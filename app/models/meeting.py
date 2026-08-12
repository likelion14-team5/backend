from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 120",
            name="ck_meetings_title_not_blank",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_meetings_status"),
        CheckConstraint(
            "max_participants BETWEEN 2 AND 4",
            name="ck_meetings_max_participants",
        ),
        CheckConstraint(
            "length(btrim(daily_room_name)) BETWEEN 1 AND 128 "
            "AND daily_room_name ~ '^[A-Za-z0-9_-]+$'",
            name="ck_meetings_daily_room_name",
        ),
        CheckConstraint(
            "length(btrim(daily_room_url)) BETWEEN 1 AND 255 AND daily_room_url ~ '^https://'",
            name="ck_meetings_daily_room_url",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL) "
            "OR (status = 'ENDED' AND ended_at IS NOT NULL)",
            name="ck_meetings_ended_at",
        ),
        Index("ix_meetings_status_created_at", "status", text("created_at DESC")),
        {"comment": "회의 최소 메타데이터. 회의 종료 후에도 종료 상태 응답을 위해 유지한다."},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    max_participants: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("4")
    )
    daily_room_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        comment="Daily private room name. public meeting API에는 반환하지 않는다.",
    )
    daily_room_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Daily private room URL. 참가자 검증 후 media-session API에서만 반환한다.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["Participant"]] = relationship(  # noqa: F821
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    pre_speech_requests: Mapped[list["PreSpeechRequest"]] = relationship(  # noqa: F821
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    speech_feedback: Mapped[list["SpeechFeedback"]] = relationship(  # noqa: F821
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
