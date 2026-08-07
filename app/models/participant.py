from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        CheckConstraint(
            "participant_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_participants_token_hash",
        ),
        CheckConstraint("role IN ('HOST', 'MEMBER')", name="ck_participants_role"),
        CheckConstraint("status IN ('JOINED', 'LEFT')", name="ck_participants_status"),
        CheckConstraint(
            "length(btrim(display_name)) BETWEEN 1 AND 50",
            name="ck_participants_display_name",
        ),
        CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name="ck_participants_country_code",
        ),
        CheckConstraint(
            "length(btrim(organization)) BETWEEN 1 AND 100",
            name="ck_participants_organization",
        ),
        CheckConstraint(
            "length(btrim(job_title)) BETWEEN 1 AND 100",
            name="ck_participants_job_title",
        ),
        CheckConstraint(
            "cardinality(languages) BETWEEN 1 AND 10",
            name="ck_participants_languages",
        ),
        CheckConstraint(
            "english_proficiency IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')",
            name="ck_participants_english_proficiency",
        ),
        CheckConstraint(
            "communication_style IN "
            "('DIRECT', 'INDIRECT', 'FACT_FOCUSED', 'EMOTION_EXPRESSIVE', 'BALANCED')",
            name="ck_participants_communication_style",
        ),
        CheckConstraint(
            "timezone IS NULL OR length(btrim(timezone)) BETWEEN 1 AND 64",
            name="ck_participants_timezone",
        ),
        CheckConstraint(
            "additional_considerations IS NULL "
            "OR length(btrim(additional_considerations)) BETWEEN 1 AND 500",
            name="ck_participants_additional_considerations",
        ),
        CheckConstraint(
            "profile_sharing_consent = TRUE",
            name="ck_participants_profile_consent",
        ),
        CheckConstraint(
            "(voice_analysis_consent = TRUE AND voice_consent_at IS NOT NULL) "
            "OR (voice_analysis_consent = FALSE AND voice_consent_at IS NULL)",
            name="ck_participants_voice_consent_at",
        ),
        CheckConstraint(
            "voice_analysis_enabled = FALSE OR voice_analysis_consent = TRUE",
            name="ck_participants_voice_enabled",
        ),
        CheckConstraint(
            "(status = 'JOINED' AND left_at IS NULL) OR (status = 'LEFT' AND left_at IS NOT NULL)",
            name="ck_participants_left_at",
        ),
        Index("ix_participants_meeting_status", "meeting_id", "status"),
        Index("ix_participants_meeting_joined_at", "meeting_id", "joined_at"),
        Index(
            "uq_participants_joined_display_name",
            "meeting_id",
            text("lower(display_name)"),
            unique=True,
            postgresql_where=text("status = 'JOINED'"),
        ),
        Index(
            "uq_participants_one_host_per_meeting",
            "meeting_id",
            unique=True,
            postgresql_where=text("role = 'HOST'"),
        ),
        {"comment": "계정이 아닌 회의 세션 참가자와 공개 프로필. 회의 종료 시 삭제한다."},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    meeting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE", name="fk_participants_meeting"),
        nullable=False,
    )
    participant_token_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        unique=True,
        comment="클라이언트에 한 번 발급한 opaque token의 SHA-256 hex digest.",
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'MEMBER'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'JOINED'"))

    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    organization: Mapped[str] = mapped_column(String(100), nullable=False)
    job_title: Mapped[str] = mapped_column(String(100), nullable=False)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="주요 사용 언어. 순서상 첫 항목을 UI의 대표 언어로 사용한다.",
    )
    english_proficiency: Mapped[str] = mapped_column(String(20), nullable=False)
    communication_style: Mapped[str] = mapped_column(String(30), nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    additional_considerations: Mapped[str | None] = mapped_column(String(500), nullable=True)

    profile_sharing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    profile_consent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    voice_analysis_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    voice_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voice_analysis_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="participants")  # noqa: F821
