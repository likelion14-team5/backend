from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import ParticipantContext, get_participant_context, get_pre_speech_service
from app.schemas.common import ApiErrorEnvelope
from app.schemas.pre_speech import PreSpeechCreateRequest, PreSpeechResultResponse
from app.services.pre_speech_service import PreSpeechService

router = APIRouter(prefix="/meetings/{meeting_id}/pre-speech", tags=["Pre-Speech"])


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
    response_model=PreSpeechResultResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPreSpeech",
    summary="F-02 발언 전 추천 생성",
    responses=error_responses(400, 401, 404, 409, 422, 502),
)
def create_pre_speech(
    request: PreSpeechCreateRequest,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[PreSpeechService, Depends(get_pre_speech_service)],
) -> PreSpeechResultResponse:
    result = service.create(context.meeting.id, context.participant.id, request)
    return PreSpeechResultResponse(data=result)


@router.get(
    "/{request_id}",
    response_model=PreSpeechResultResponse,
    operation_id="getPreSpeech",
    summary="F-02 결과 조회",
    responses=error_responses(401, 404, 409),
)
def get_pre_speech(
    request_id: UUID,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[PreSpeechService, Depends(get_pre_speech_service)],
) -> PreSpeechResultResponse:
    result = service.get(context.meeting.id, context.participant.id, request_id)
    return PreSpeechResultResponse(data=result)


@router.post(
    "/{request_id}/regenerate",
    response_model=PreSpeechResultResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="regeneratePreSpeech",
    summary="F-02 재생성",
    responses=error_responses(401, 404, 409, 502),
)
def regenerate_pre_speech(
    request_id: UUID,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[PreSpeechService, Depends(get_pre_speech_service)],
) -> PreSpeechResultResponse:
    result = service.regenerate(context.meeting.id, context.participant.id, request_id)
    return PreSpeechResultResponse(data=result)
