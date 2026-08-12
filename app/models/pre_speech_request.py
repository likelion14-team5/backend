from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PreSpeechRequest(Base):
    __tablename__ = "pre_speech_requests"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(input_ko)) BETWEEN 1 AND 1000",
            name="ck_pre_speech_input_ko",
        ),
        CheckConstraint(
            "meeting_context IS NULL OR length(btrim(meeting_context)) BETWEEN 1 AND 1000",
            name="ck_pre_speech_meeting_context",
        ),
        CheckConstraint(
            "length(btrim(recommended_expression_en)) BETWEEN 1 AND 1000",
            name="ck_pre_speech_recommended_expression",
        ),
        CheckConstraint(
            "length(btrim(recommendation_reason_ko)) BETWEEN 1 AND 1000",
            name="ck_pre_speech_recommendation_reason",
        ),
        CheckConstraint(
            "target_participant_id IS NULL OR target_participant_id <> requester_participant_id",
            name="ck_pre_speech_not_self_target",
        ),
        Index("ix_pre_speech_meeting_created_at", "meeting_id", text("created_at DESC")),
        Index(
            "ix_pre_speech_requester_created_at",
            "requester_participant_id",
            text("created_at DESC"),
        ),
        {"comment": "F-02 OpenAI 성공 요청/결과. 실패 호출은 저장하지 않는다."},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    meeting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE", name="fk_pre_speech_meeting"),
        nullable=False,
    )
    requester_participant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE", name="fk_pre_speech_requester"),
        nullable=False,
    )
    target_participant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE", name="fk_pre_speech_target"),
        nullable=True,
    )
    parent_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pre_speech_requests.id", ondelete="SET NULL", name="fk_pre_speech_parent"),
        nullable=True,
    )
    input_ko: Mapped[str] = mapped_column(String(1000), nullable=False)
    meeting_context: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recommended_expression_en: Mapped[str] = mapped_column(String(1000), nullable=False)
    recommendation_reason_ko: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="pre_speech_requests")  # noqa: F821
