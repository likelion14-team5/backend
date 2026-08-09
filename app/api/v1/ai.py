from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.ai import (
    PreSpeechRequest,
    PreSpeechResponse,
    SpeechFeedbackRequest,
    SpeechFeedbackResponse,
)
from app.schemas.common import ApiErrorEnvelope
from app.services.ai_service import AiService, get_ai_service

router = APIRouter(prefix="/ai", tags=["AI"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        code: {
            "model": ApiErrorEnvelope,
            "description": "명세화된 API 오류",
        }
        for code in status_codes
    }


@router.post(
    "/pre-speech",
    response_model=PreSpeechResponse,
    operation_id="generatePreSpeech",
    summary="한국어 문장을 상대방 프로필에 맞는 영어 표현으로 변환",
    responses=error_responses(422, 502),
)
def pre_speech(
    request: PreSpeechRequest,
    service: Annotated[AiService, Depends(get_ai_service)],
) -> PreSpeechResponse:
    return PreSpeechResponse(data=service.generate_pre_speech(request))


@router.post(
    "/speech-feedback",
    response_model=SpeechFeedbackResponse,
    operation_id="generateSpeechFeedback",
    summary="영어 발언이 상대방에게 오해나 마찰을 일으킬 가능성이 있는지 점검",
    responses=error_responses(422, 502),
)
def speech_feedback(
    request: SpeechFeedbackRequest,
    service: Annotated[AiService, Depends(get_ai_service)],
) -> SpeechFeedbackResponse:
    return SpeechFeedbackResponse(data=service.generate_speech_feedback(request))
