from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SpeechFeedback(Base):
    __tablename__ = "speech_feedback"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(detected_text)) BETWEEN 1 AND 2000",
            name="ck_speech_feedback_detected_text",
        ),
        CheckConstraint(
            "normalized_text_hash ~ '^[0-9a-f]{64}$'",
            name="ck_speech_feedback_text_hash",
        ),
        CheckConstraint(
            "stt_confidence IS NULL OR stt_confidence BETWEEN 0 AND 1",
            name="ck_speech_feedback_confidence",
        ),
        CheckConstraint(
            "risk_type IN "
            "('DIRECT_REJECTION', 'PERSONAL_ATTACK', 'AMBIGUOUS_INTENT', "
            "'IDIOM_OR_JOKE', 'PROFILE_CONFLICT', 'OTHER')",
            name="ck_speech_feedback_risk_type",
        ),
        CheckConstraint(
            "length(btrim(explanation_ko)) BETWEEN 1 AND 1000",
            name="ck_speech_feedback_explanation",
        ),
        CheckConstraint(
            "length(btrim(alternative_expression_en)) BETWEEN 1 AND 1000",
            name="ck_speech_feedback_alternative",
        ),
        CheckConstraint(
            "display_state IN ('VISIBLE', 'DISMISSED')",
            name="ck_speech_feedback_display_state",
        ),
        CheckConstraint(
            "(display_state = 'VISIBLE' AND dismissed_at IS NULL) "
            "OR (display_state = 'DISMISSED' AND dismissed_at IS NOT NULL)",
            name="ck_speech_feedback_dismissed_at",
        ),
        Index("ix_speech_feedback_meeting_created_at", "meeting_id", text("created_at DESC")),
        Index(
            "ix_speech_feedback_participant_created_at",
            "participant_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_speech_feedback_duplicate_window",
            "participant_id",
            "normalized_text_hash",
            "risk_type",
            text("created_at DESC"),
        ),
        {
            "comment": (
                "F-03에서 위험이 감지된 피드백만 저장. detected_text는 회의 종료 시 함께 삭제된다."
            )
        },
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    meeting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE", name="fk_speech_feedback_meeting"),
        nullable=False,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE", name="fk_speech_feedback_participant"),
        nullable=False,
    )
    detected_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    normalized_text_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    stt_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    transcript_may_be_inaccurate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    risk_type: Mapped[str] = mapped_column(String(40), nullable=False)
    explanation_ko: Mapped[str] = mapped_column(String(1000), nullable=False)
    alternative_expression_en: Mapped[str] = mapped_column(String(1000), nullable=False)
    display_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'VISIBLE'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="speech_feedback")  # noqa: F821
