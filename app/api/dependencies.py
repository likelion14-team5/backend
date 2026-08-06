from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.meeting import Meeting
from app.models.participant import Participant
from app.schemas.meeting import MeetingStatus, ParticipantStatus
from app.security.participant_token import hash_participant_token
from app.services.daily_service import DailyService, get_daily_service
from app.services.meeting_service import MeetingService


@dataclass(frozen=True, slots=True)
class ParticipantContext:
    meeting: Meeting
    participant: Participant


participant_token_header = APIKeyHeader(
    name="X-Participant-Token",
    scheme_name="ParticipantToken",
    description="회의 생성 또는 입장 성공 시 한 번 발급되는 회의 범위 opaque token",
    auto_error=False,
)


def get_participant_context(
    meeting_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    participant_token: Annotated[str | None, Depends(participant_token_header)],
) -> ParticipantContext:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise AppError(404, "MEETING_NOT_FOUND", "회의를 찾을 수 없습니다.")
    if meeting.status == MeetingStatus.ENDED.value:
        raise AppError(409, "MEETING_ENDED", "이미 종료된 회의입니다.")
    if not participant_token:
        raise AppError(401, "INVALID_PARTICIPANT_TOKEN", "참가자 세션을 확인할 수 없습니다.")

    participant = db.scalar(
        select(Participant).where(
            Participant.meeting_id == meeting.id,
            Participant.participant_token_hash == hash_participant_token(participant_token),
        )
    )
    if participant is None:
        raise AppError(401, "INVALID_PARTICIPANT_TOKEN", "참가자 세션을 확인할 수 없습니다.")
    if participant.status == ParticipantStatus.LEFT.value:
        raise AppError(409, "PARTICIPANT_LEFT", "이미 회의에서 나간 참가자입니다.")
    return ParticipantContext(meeting=meeting, participant=participant)


def get_meeting_service(
    db: Annotated[Session, Depends(get_db)],
    daily: Annotated[DailyService, Depends(get_daily_service)],
) -> MeetingService:
    return MeetingService(db=db, daily=daily)
