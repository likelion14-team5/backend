from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.meeting import Meeting
from app.models.participant import Participant
from app.schemas.common import CountMeta
from app.schemas.meeting import (
    MeetingContext,
    MeetingCreateData,
    MeetingCreateRequest,
    MeetingStatus,
    MeetingSummary,
    ParticipantJoinData,
    ParticipantJoinRequest,
    ParticipantListResponse,
    ParticipantProfile,
    ParticipantRole,
    ParticipantSessionSummary,
    ParticipantStatus,
    ParticipantSummary,
    ProfileInput,
    ProfileUpdateRequest,
    ProfileView,
    PublicMeeting,
    VideoConfig,
)
from app.security.participant_token import create_participant_token
from app.services.daily_service import DailyService


class MeetingService:
    def __init__(
        self,
        db: Session,
        daily: DailyService,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.daily = daily
        self.settings = settings or get_settings()

    def _joined_count(self, meeting_id: UUID) -> int:
        statement = select(func.count(Participant.id)).where(
            Participant.meeting_id == meeting_id,
            Participant.status == ParticipantStatus.JOINED.value,
        )
        return int(self.db.scalar(statement) or 0)

    def _meeting_summary(self, meeting: Meeting) -> MeetingSummary:
        return MeetingSummary(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status,
            max_participants=meeting.max_participants,
            current_participants=self._joined_count(meeting.id),
            created_at=meeting.created_at,
            ended_at=meeting.ended_at,
        )

    @staticmethod
    def _participant_session(participant: Participant) -> ParticipantSessionSummary:
        return ParticipantSessionSummary(
            id=participant.id,
            display_name=participant.display_name,
            role=participant.role,
            status=participant.status,
        )

    @staticmethod
    def _profile_view(participant: Participant) -> ProfileView:
        return ProfileView(
            display_name=participant.display_name,
            country_code=participant.country_code,
            organization=participant.organization,
            job_title=participant.job_title,
            languages=list(participant.languages),
            english_proficiency=participant.english_proficiency,
            communication_style=participant.communication_style,
            timezone=participant.timezone,
            additional_considerations=participant.additional_considerations,
        )

    @classmethod
    def participant_profile(cls, participant: Participant) -> ParticipantProfile:
        return ParticipantProfile(
            id=participant.id,
            role=participant.role,
            status=participant.status,
            profile=cls._profile_view(participant),
            voice_analysis_enabled=participant.voice_analysis_enabled,
            joined_at=participant.joined_at,
        )

    @staticmethod
    def _profile_columns(profile: ProfileInput) -> dict[str, object]:
        return profile.model_dump(mode="json")

    @staticmethod
    def _voice_consent_time(consented: bool) -> datetime | None:
        return datetime.now(UTC) if consented else None

    def create_meeting(self, request: MeetingCreateRequest) -> MeetingCreateData:
        daily_room = self.daily.create_room(request.max_participants)
        participant_token = create_participant_token()
        try:
            meeting = Meeting(
                title=request.title,
                max_participants=request.max_participants,
                daily_room_name=daily_room.name,
                daily_room_url=daily_room.url,
            )
            self.db.add(meeting)
            self.db.flush()
            participant = Participant(
                meeting_id=meeting.id,
                participant_token_hash=participant_token.digest,
                role=ParticipantRole.HOST.value,
                status=ParticipantStatus.JOINED.value,
                **self._profile_columns(request.host_profile),
                profile_sharing_consent=request.profile_sharing_consent,
                voice_analysis_consent=request.voice_analysis_consent,
                voice_consent_at=self._voice_consent_time(request.voice_analysis_consent),
                voice_analysis_enabled=request.voice_analysis_consent,
            )
            self.db.add(participant)
            self.db.commit()
            self.db.refresh(meeting)
            self.db.refresh(participant)
        except Exception:
            self.db.rollback()
            self.daily.delete_room_best_effort(daily_room.name)
            raise

        share_url = f"{self.settings.public_app_url.rstrip('/')}/join/{meeting.id}"
        return MeetingCreateData(
            meeting=self._meeting_summary(meeting),
            participant=self._participant_session(participant),
            participant_token=participant_token.raw,
            share_url=share_url,
        )

    def get_public_meeting(self, meeting_id: UUID) -> PublicMeeting:
        meeting = self.db.get(Meeting, meeting_id)
        if meeting is None:
            raise AppError(404, "MEETING_NOT_FOUND", "회의를 찾을 수 없습니다.")
        current_participants = self._joined_count(meeting.id)
        return PublicMeeting(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status,
            max_participants=meeting.max_participants,
            current_participants=current_participants,
            can_join=(
                meeting.status == MeetingStatus.ACTIVE.value
                and current_participants < meeting.max_participants
            ),
        )

    def join_meeting(
        self, meeting_id: UUID, request: ParticipantJoinRequest
    ) -> ParticipantJoinData:
        meeting = self.db.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())
        if meeting is None:
            self.db.rollback()
            raise AppError(404, "MEETING_NOT_FOUND", "회의를 찾을 수 없습니다.")
        if meeting.status == MeetingStatus.ENDED.value:
            self.db.rollback()
            raise AppError(409, "MEETING_ENDED", "이미 종료된 회의입니다.")
        if self._joined_count(meeting.id) >= meeting.max_participants:
            self.db.rollback()
            raise AppError(409, "MEETING_FULL", "회의 정원이 가득 찼습니다.")

        duplicate_name = self.db.scalar(
            select(Participant.id).where(
                Participant.meeting_id == meeting.id,
                Participant.status == ParticipantStatus.JOINED.value,
                func.lower(Participant.display_name) == request.profile.display_name.lower(),
            )
        )
        if duplicate_name is not None:
            self.db.rollback()
            raise AppError(409, "DISPLAY_NAME_TAKEN", "이미 사용 중인 표시 이름입니다.")

        participant_token = create_participant_token()
        participant = Participant(
            meeting_id=meeting.id,
            participant_token_hash=participant_token.digest,
            role=ParticipantRole.MEMBER.value,
            status=ParticipantStatus.JOINED.value,
            **self._profile_columns(request.profile),
            profile_sharing_consent=request.profile_sharing_consent,
            voice_analysis_consent=request.voice_analysis_consent,
            voice_consent_at=self._voice_consent_time(request.voice_analysis_consent),
            voice_analysis_enabled=request.voice_analysis_consent,
        )
        self.db.add(participant)
        try:
            self.db.commit()
            self.db.refresh(participant)
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_participants_joined_display_name" in str(exc.orig):
                raise AppError(
                    409,
                    "DISPLAY_NAME_TAKEN",
                    "이미 사용 중인 표시 이름입니다.",
                ) from exc
            raise
        return ParticipantJoinData(
            participant=self._participant_session(participant),
            participant_token=participant_token.raw,
            meeting_path=f"/meetings/{meeting.id}",
        )

    def meeting_context(self, meeting: Meeting, participant: Participant) -> MeetingContext:
        return MeetingContext(
            meeting=self._meeting_summary(meeting),
            me=self.participant_profile(participant),
            video=VideoConfig(room_name=meeting.daily_room_name),
        )

    @staticmethod
    def _local_time(timezone_name: str | None) -> str | None:
        if timezone_name is None:
            return None
        try:
            return datetime.now(ZoneInfo(timezone_name)).isoformat(timespec="minutes")
        except ZoneInfoNotFoundError:
            return None

    def list_participants(self, meeting_id: UUID) -> ParticipantListResponse:
        participants = list(
            self.db.scalars(
                select(Participant)
                .where(
                    Participant.meeting_id == meeting_id,
                    Participant.status == ParticipantStatus.JOINED.value,
                )
                .order_by(Participant.joined_at, Participant.id)
            )
        )
        data = [
            ParticipantSummary(
                id=participant.id,
                display_name=participant.display_name,
                organization=participant.organization,
                job_title=participant.job_title,
                primary_language=participant.languages[0],
                timezone=participant.timezone,
                local_time=self._local_time(participant.timezone),
                role=participant.role,
                status=participant.status,
                joined_at=participant.joined_at,
            )
            for participant in participants
        ]
        return ParticipantListResponse(data=data, meta=CountMeta(count=len(data)))

    def get_participant_profile(self, meeting_id: UUID, participant_id: UUID) -> ParticipantProfile:
        participant = self.db.scalar(
            select(Participant).where(
                Participant.id == participant_id,
                Participant.meeting_id == meeting_id,
                Participant.status == ParticipantStatus.JOINED.value,
            )
        )
        if participant is None:
            raise AppError(404, "PARTICIPANT_NOT_FOUND", "참가자를 찾을 수 없습니다.")
        return self.participant_profile(participant)

    def update_profile(
        self,
        participant: Participant,
        request: ProfileUpdateRequest,
    ) -> ParticipantProfile:
        changes = request.model_dump(exclude_unset=True, mode="json")
        for field, value in changes.items():
            setattr(participant, field, value)
        participant.updated_at = datetime.now(UTC)
        try:
            self.db.commit()
            self.db.refresh(participant)
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_participants_joined_display_name" in str(exc.orig):
                raise AppError(
                    409,
                    "DISPLAY_NAME_TAKEN",
                    "이미 사용 중인 표시 이름입니다.",
                ) from exc
            raise
        return self.participant_profile(participant)

    def set_voice_analysis(self, participant: Participant, enabled: bool) -> ParticipantProfile:
        if enabled and not participant.voice_analysis_consent:
            raise AppError(403, "VOICE_CONSENT_REQUIRED", "음성 분석 동의가 필요합니다.")
        participant.voice_analysis_enabled = enabled
        participant.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(participant)
        return self.participant_profile(participant)

    def leave(self, participant: Participant) -> None:
        participant.status = ParticipantStatus.LEFT.value
        participant.left_at = datetime.now(UTC)
        participant.updated_at = participant.left_at
        self.db.commit()

    def end(self, meeting: Meeting) -> None:
        room_name = meeting.daily_room_name
        meeting.status = MeetingStatus.ENDED.value
        meeting.ended_at = datetime.now(UTC)
        self.db.execute(
            delete(Participant)
            .where(Participant.meeting_id == meeting.id)
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        self.daily.delete_room_best_effort(room_name)
