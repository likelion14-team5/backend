from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, CountMeta

Transcript = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
RecentContextText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class RiskType(StrEnum):
    DIRECT_REJECTION = "DIRECT_REJECTION"
    PERSONAL_ATTACK = "PERSONAL_ATTACK"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    IDIOM_OR_JOKE = "IDIOM_OR_JOKE"
    PROFILE_CONFLICT = "PROFILE_CONFLICT"
    OTHER = "OTHER"


class FeedbackDisplayState(StrEnum):
    VISIBLE = "VISIBLE"
    DISMISSED = "DISMISSED"


class SpeechFeedbackAnalyzeRequest(ApiModel):
    transcript: Transcript
    stt_confidence: float | None = Field(default=None, ge=0, le=1)
    stt_source: Literal["WEB_SPEECH"] = "WEB_SPEECH"
    recent_context: RecentContextText | None = None


class SpeechFeedbackDetail(ApiModel):
    id: UUID
    detected_text: str
    risk_type: RiskType
    explanation_ko: str
    alternative_expression_en: str
    transcript_may_be_inaccurate: bool
    display_state: FeedbackDisplayState


class SpeechFeedbackAnalyzeResult(ApiModel):
    risk_detected: bool
    feedback: SpeechFeedbackDetail | None
    suppressed_duplicate: bool


class SpeechFeedbackAnalyzeResponse(ApiModel):
    data: SpeechFeedbackAnalyzeResult


class SpeechFeedbackListItem(ApiModel):
    id: UUID
    detected_text: str
    risk_type: RiskType
    explanation_ko: str
    alternative_expression_en: str
    transcript_may_be_inaccurate: bool
    display_state: FeedbackDisplayState
    created_at: datetime
    dismissed_at: datetime | None


class SpeechFeedbackListResponse(ApiModel):
    data: list[SpeechFeedbackListItem]
    meta: CountMeta


class SpeechFeedbackDismissRequest(ApiModel):
    display_state: Literal[FeedbackDisplayState.DISMISSED] = FeedbackDisplayState.DISMISSED


class SpeechFeedbackDismissResponse(ApiModel):
    data: SpeechFeedbackListItem
