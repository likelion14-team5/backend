from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import (
    ParticipantContext,
    get_meeting_service,
    get_participant_context,
)
from app.core.errors import AppError
from app.schemas.common import ApiErrorEnvelope
from app.schemas.meeting import (
    MediaSession,
    MediaSessionResponse,
    MeetingContextResponse,
    MeetingCreateRequest,
    MeetingCreateResponse,
    ParticipantJoinRequest,
    ParticipantJoinResponse,
    ParticipantListResponse,
    ParticipantProfileResponse,
    ParticipantRole,
    ProfileUpdateRequest,
    PublicMeetingResponse,
    VoiceAnalysisToggleRequest,
)
from app.services.meeting_service import MeetingService

router = APIRouter(prefix="/meetings")


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        code: {
            "model": ApiErrorEnvelope,
            "description": "명세화된 API 오류",
        }
        for code in status_codes
    }


@router.post(
    "",
    response_model=MeetingCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Meetings"],
    operation_id="createMeeting",
    summary="회의와 HOST 프로필 생성",
    responses=error_responses(422, 500, 502),
)
def create_meeting(
    request: MeetingCreateRequest,
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> MeetingCreateResponse:
    return MeetingCreateResponse(data=service.create_meeting(request))


@router.get(
    "/{meeting_id}/public",
    response_model=PublicMeetingResponse,
    tags=["Meetings"],
    operation_id="getPublicMeeting",
    summary="입장 페이지용 공개 회의 정보 조회",
    responses=error_responses(404),
)
def get_public_meeting(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> PublicMeetingResponse:
    return PublicMeetingResponse(data=service.get_public_meeting(meeting_id))


@router.get(
    "/{meeting_id}",
    response_model=MeetingContextResponse,
    tags=["Meetings"],
    operation_id="getMeetingContext",
    summary="회의 화면 초기 컨텍스트 조회",
    responses=error_responses(401, 404, 409),
)
def get_meeting_context(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> MeetingContextResponse:
    return MeetingContextResponse(
        data=service.meeting_context(context.meeting, context.participant)
    )


@router.post(
    "/{meeting_id}/media-session",
    response_model=MediaSessionResponse,
    tags=["Meetings"],
    operation_id="createMediaSession",
    summary="Daily 회의 입장 세션 발급",
    responses=error_responses(401, 404, 409, 502),
)
def create_media_session(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> MediaSessionResponse:
    media_session = service.daily.create_meeting_token(
        room_name=context.meeting.daily_room_name,
        participant_id=context.participant.id,
        display_name=context.participant.display_name,
        is_owner=context.participant.role == ParticipantRole.HOST.value,
    )
    return MediaSessionResponse(
        data=MediaSession(
            room_url=context.meeting.daily_room_url,
            meeting_token=media_session.token,
            expires_at=media_session.expires_at,
        )
    )


@router.post(
    "/{meeting_id}/participants",
    response_model=ParticipantJoinResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Participants"],
    operation_id="joinMeeting",
    summary="프로필을 입력하고 회의 입장",
    responses=error_responses(404, 409, 422),
)
def join_meeting(
    meeting_id: UUID,
    request: ParticipantJoinRequest,
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> ParticipantJoinResponse:
    return ParticipantJoinResponse(data=service.join_meeting(meeting_id, request))


@router.get(
    "/{meeting_id}/participants",
    response_model=ParticipantListResponse,
    tags=["Participants"],
    operation_id="listParticipants",
    summary="같은 회의의 참가자 요약 목록",
    responses=error_responses(401, 404, 409),
)
def list_participants(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> ParticipantListResponse:
    return service.list_participants(context.meeting.id)


@router.get(
    "/{meeting_id}/participants/{participant_id}",
    response_model=ParticipantProfileResponse,
    tags=["Participants"],
    operation_id="getParticipantProfile",
    summary="같은 회의 참가자의 공개 프로필 상세",
    responses=error_responses(401, 404, 409),
)
def get_participant_profile(
    participant_id: UUID,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> ParticipantProfileResponse:
    return ParticipantProfileResponse(
        data=service.get_participant_profile(context.meeting.id, participant_id)
    )


@router.patch(
    "/{meeting_id}/participants/me/profile",
    response_model=ParticipantProfileResponse,
    tags=["Participants"],
    operation_id="updateMyProfile",
    summary="현재 참가자의 프로필 수정",
    responses=error_responses(401, 404, 409, 422),
)
def update_my_profile(
    request: ProfileUpdateRequest,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> ParticipantProfileResponse:
    return ParticipantProfileResponse(data=service.update_profile(context.participant, request))


@router.patch(
    "/{meeting_id}/participants/me/voice-analysis",
    response_model=ParticipantProfileResponse,
    tags=["Participants"],
    operation_id="setVoiceAnalysis",
    summary="F-03 음성 분석 ON/OFF",
    responses=error_responses(401, 403, 404, 409),
)
def set_voice_analysis(
    request: VoiceAnalysisToggleRequest,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> ParticipantProfileResponse:
    return ParticipantProfileResponse(
        data=service.set_voice_analysis(context.participant, request.voice_analysis_enabled)
    )


@router.post(
    "/{meeting_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Meetings"],
    operation_id="leaveMeeting",
    summary="현재 참가자 회의 나가기",
    responses=error_responses(401, 404, 409),
)
def leave_meeting(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> Response:
    service.leave(context.participant)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{meeting_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Meetings"],
    operation_id="endMeeting",
    summary="HOST가 회의를 종료하고 세션 개인정보 삭제",
    responses=error_responses(401, 403, 404, 409),
)
def end_meeting(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[MeetingService, Depends(get_meeting_service)],
) -> Response:
    if context.participant.role != ParticipantRole.HOST.value:
        raise AppError(403, "HOST_REQUIRED", "회의 종료는 HOST만 할 수 있습니다.")
    service.end(context.meeting)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
