from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel

CounterpartProficiency = Literal["초급", "중급", "고급"]
CounterpartCommunicationStyle = Literal[
    "직접적", "균형적", "완곡한", "사실 중심적", "감정 표현이 풍부한"
]

SpeechFeedbackType = Literal[
    "직접적 거절",
    "공격적 표현",
    "모호한 표현",
    "관용어/속어",
    "고려사항 충돌",
]


class CounterpartProfile(ApiModel):
    proficiency: CounterpartProficiency = Field(description="상대방 영어 숙련도")
    communication_style: CounterpartCommunicationStyle = Field(description="상대방 선호 소통 방식")
    job_role: str = Field(min_length=1, description="상대방 직무")
    additional_considerations: str | None = Field(default=None, description="추가 고려사항")


class PreSpeechRequest(ApiModel):
    korean_text: str = Field(min_length=1, description="변환할 한국어 문장")
    counterpart_profile: CounterpartProfile
    meeting_context: str = Field(min_length=1, description="회의 맥락")


class PreSpeechResult(ApiModel):
    expression: str
    reason: str


class PreSpeechResponse(ApiModel):
    data: PreSpeechResult


class SpeechFeedbackRequest(ApiModel):
    english_text: str = Field(min_length=1, description="분석할 영어 발언")
    recent_messages: list[str] = Field(
        default_factory=list, max_length=5, description="최근 대화 (시간순, 최대 5개)"
    )
    counterpart_profile: CounterpartProfile


class SpeechFeedbackResult(ApiModel):
    flagged: bool
    original_text: str
    type: SpeechFeedbackType | None = None
    reason: str | None = None
    alternative: str | None = None


class SpeechFeedbackResponse(ApiModel):
    data: SpeechFeedbackResult
