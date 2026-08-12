from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyHttpUrl,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import ApiModel, CountMeta

NonBlank50 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
NonBlank100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NonBlank120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
NonBlank500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
TimezoneName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class MeetingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class ParticipantRole(StrEnum):
    HOST = "HOST"
    MEMBER = "MEMBER"


class ParticipantStatus(StrEnum):
    JOINED = "JOINED"
    LEFT = "LEFT"


class EnglishProficiency(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class CommunicationStyle(StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    FACT_FOCUSED = "FACT_FOCUSED"
    EMOTION_EXPRESSIVE = "EMOTION_EXPRESSIVE"
    BALANCED = "BALANCED"


class ProfileInput(ApiModel):
    display_name: NonBlank50
    country_code: CountryCode
    organization: NonBlank100
    job_title: NonBlank100
    languages: Annotated[
        list[Language],
        Field(min_length=1, max_length=10, json_schema_extra={"uniqueItems": True}),
    ]
    english_proficiency: EnglishProficiency
    communication_style: CommunicationStyle
    timezone: TimezoneName | None = None
    additional_considerations: NonBlank500 | None = None

    @field_validator("languages")
    @classmethod
    def languages_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [language.casefold() for language in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("사용 언어는 중복될 수 없습니다.")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("유효한 IANA 시간대를 입력해주세요.") from exc
        return value


class ProfileUpdateRequest(ApiModel):
    model_config = ConfigDict(json_schema_extra={"minProperties": 1})

    display_name: NonBlank50 = None  # type: ignore[assignment]
    country_code: CountryCode = None  # type: ignore[assignment]
    organization: NonBlank100 = None  # type: ignore[assignment]
    job_title: NonBlank100 = None  # type: ignore[assignment]
    languages: Annotated[
        list[Language],
        Field(min_length=1, max_length=10, json_schema_extra={"uniqueItems": True}),
    ] = None  # type: ignore[assignment]
    english_proficiency: EnglishProficiency = None  # type: ignore[assignment]
    communication_style: CommunicationStyle = None  # type: ignore[assignment]
    timezone: TimezoneName | None = None
    additional_considerations: NonBlank500 | None = None

    @field_validator("languages")
    @classmethod
    def languages_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [language.casefold() for language in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("사용 언어는 중복될 수 없습니다.")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("유효한 IANA 시간대를 입력해주세요.") from exc
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("수정할 프로필 필드를 하나 이상 입력해주세요.")
        return self


class MeetingCreateRequest(ApiModel):
    title: NonBlank120
    max_participants: int = Field(ge=2, le=4)
    host_profile: ProfileInput
    profile_sharing_consent: Literal[True]
    voice_analysis_consent: bool


class VoiceAnalysisToggleRequest(ApiModel):
    voice_analysis_enabled: bool


class ParticipantJoinRequest(ApiModel):
    profile: ProfileInput
    profile_sharing_consent: Literal[True]
    voice_analysis_consent: bool


class MeetingSummary(ApiModel):
    id: UUID
    title: str
    status: MeetingStatus
    max_participants: int
    current_participants: int = Field(ge=0, le=4)
    created_at: datetime
    ended_at: datetime | None = None


class ParticipantSessionSummary(ApiModel):
    id: UUID
    display_name: str
    role: ParticipantRole
    status: ParticipantStatus


class ParticipantSummary(ApiModel):
    id: UUID
    display_name: str
    organization: str
    job_title: str
    primary_language: str
    timezone: str | None = None
    local_time: str | None = None
    role: ParticipantRole
    status: ParticipantStatus
    joined_at: datetime


class ProfileView(ProfileInput):
    pass


class ParticipantProfile(ApiModel):
    id: UUID
    role: ParticipantRole
    status: ParticipantStatus
    profile: ProfileView
    voice_analysis_enabled: bool
    joined_at: datetime


class PublicMeeting(ApiModel):
    id: UUID
    title: str
    status: MeetingStatus
    max_participants: int
    current_participants: int
    can_join: bool


class VideoConfig(ApiModel):
    provider: Literal["DAILY"] = "DAILY"
    room_name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ]


class MeetingContext(ApiModel):
    meeting: MeetingSummary
    me: ParticipantProfile
    video: VideoConfig


class MediaSession(ApiModel):
    provider: Literal["DAILY"] = "DAILY"
    room_url: AnyHttpUrl
    meeting_token: str = Field(min_length=20)
    expires_at: datetime


class MeetingCreateData(ApiModel):
    meeting: MeetingSummary
    participant: ParticipantSessionSummary
    participant_token: str = Field(min_length=32)
    share_url: AnyHttpUrl


class ParticipantJoinData(ApiModel):
    participant: ParticipantSessionSummary
    participant_token: str = Field(min_length=32)
    meeting_path: str


class MeetingCreateResponse(ApiModel):
    data: MeetingCreateData


class ParticipantJoinResponse(ApiModel):
    data: ParticipantJoinData


class PublicMeetingResponse(ApiModel):
    data: PublicMeeting


class MeetingContextResponse(ApiModel):
    data: MeetingContext


class MediaSessionResponse(ApiModel):
    data: MediaSession


class ParticipantListResponse(ApiModel):
    data: list[ParticipantSummary]
    meta: CountMeta


class ParticipantProfileResponse(ApiModel):
    data: ParticipantProfile
