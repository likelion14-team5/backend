from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

from app.schemas.common import ApiModel

InputKo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
MeetingContextText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
RecommendedExpression = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
RecommendationReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class PreSpeechCreateRequest(ApiModel):
    input_ko: InputKo
    target_participant_id: UUID | None = None
    meeting_context: MeetingContextText | None = None


class PreSpeechResult(ApiModel):
    id: UUID
    input_ko: str
    target_participant_id: UUID | None
    meeting_context: str | None
    recommended_expression_en: str
    recommendation_reason_ko: str
    parent_request_id: UUID | None
    created_at: datetime


class PreSpeechResultResponse(ApiModel):
    data: PreSpeechResult
