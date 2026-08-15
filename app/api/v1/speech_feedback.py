from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    ParticipantContext,
    get_participant_context,
    get_speech_feedback_service,
)
from app.schemas.common import ApiErrorEnvelope, CountMeta
from app.schemas.speech_feedback import (
    SpeechFeedbackAnalyzeRequest,
    SpeechFeedbackAnalyzeResponse,
    SpeechFeedbackDismissResponse,
    SpeechFeedbackListResponse,
)
from app.services.speech_feedback_service import SpeechFeedbackService

router = APIRouter(prefix="/meetings/{meeting_id}/speech-feedback", tags=["Speech-Feedback"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        code: {
            "model": ApiErrorEnvelope,
            "description": "명세화된 API 오류",
        }
        for code in status_codes
    }


@router.post(
    "/analyze",
    response_model=SpeechFeedbackAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="analyzeSpeechFeedback",
    summary="F-03 final transcript 분석",
    responses=error_responses(401, 403, 404, 409, 422, 502),
)
def analyze_speech_feedback(
    request: SpeechFeedbackAnalyzeRequest,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[SpeechFeedbackService, Depends(get_speech_feedback_service)],
) -> SpeechFeedbackAnalyzeResponse:
    result = service.analyze(context.meeting.id, context.participant, request)
    return SpeechFeedbackAnalyzeResponse(data=result)


@router.get(
    "",
    response_model=SpeechFeedbackListResponse,
    operation_id="listSpeechFeedback",
    summary="내 F-03 피드백 목록",
    responses=error_responses(401, 404, 409),
)
def list_speech_feedback(
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[SpeechFeedbackService, Depends(get_speech_feedback_service)],
) -> SpeechFeedbackListResponse:
    items = service.list(context.meeting.id, context.participant.id)
    return SpeechFeedbackListResponse(data=items, meta=CountMeta(count=len(items)))


@router.patch(
    "/{feedback_id}",
    response_model=SpeechFeedbackDismissResponse,
    operation_id="dismissSpeechFeedback",
    summary="내 피드백 닫기",
    responses=error_responses(401, 404, 409),
)
def dismiss_speech_feedback(
    feedback_id: UUID,
    context: Annotated[ParticipantContext, Depends(get_participant_context)],
    service: Annotated[SpeechFeedbackService, Depends(get_speech_feedback_service)],
) -> SpeechFeedbackDismissResponse:
    result = service.dismiss(context.meeting.id, context.participant.id, feedback_id)
    return SpeechFeedbackDismissResponse(data=result)
