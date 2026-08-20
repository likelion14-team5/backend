"""Create pre_speech_requests and speech_feedback tables.

Revision ID: 20260812_0002
Revises: 20260806_0001
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260812_0002"
down_revision: str | None = "20260806_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pre_speech_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL,
            requester_participant_id UUID NOT NULL,
            target_participant_id UUID NULL,
            parent_request_id UUID NULL,
            input_ko VARCHAR(1000) NOT NULL,
            meeting_context VARCHAR(1000) NULL,
            recommended_expression_en VARCHAR(1000) NOT NULL,
            recommendation_reason_ko VARCHAR(1000) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_pre_speech_meeting FOREIGN KEY (meeting_id)
                REFERENCES meetings (id) ON DELETE CASCADE,
            CONSTRAINT fk_pre_speech_requester FOREIGN KEY (requester_participant_id)
                REFERENCES participants (id) ON DELETE CASCADE,
            CONSTRAINT fk_pre_speech_target FOREIGN KEY (target_participant_id)
                REFERENCES participants (id) ON DELETE CASCADE,
            CONSTRAINT fk_pre_speech_parent FOREIGN KEY (parent_request_id)
                REFERENCES pre_speech_requests (id) ON DELETE SET NULL,
            CONSTRAINT ck_pre_speech_input_ko
                CHECK (length(btrim(input_ko)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_pre_speech_meeting_context CHECK (
                meeting_context IS NULL
                OR length(btrim(meeting_context)) BETWEEN 1 AND 1000
            ),
            CONSTRAINT ck_pre_speech_recommended_expression
                CHECK (length(btrim(recommended_expression_en)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_pre_speech_recommendation_reason
                CHECK (length(btrim(recommendation_reason_ko)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_pre_speech_not_self_target CHECK (
                target_participant_id IS NULL
                OR target_participant_id <> requester_participant_id
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pre_speech_meeting_created_at "
        "ON pre_speech_requests (meeting_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_pre_speech_requester_created_at "
        "ON pre_speech_requests (requester_participant_id, created_at DESC)"
    )
    op.execute(
        "COMMENT ON TABLE pre_speech_requests IS "
        "'F-02 OpenAI 성공 요청/결과. 실패 호출은 저장하지 않는다.'"
    )

    op.execute(
        """
        CREATE TABLE speech_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL,
            participant_id UUID NOT NULL,
            detected_text VARCHAR(2000) NOT NULL,
            normalized_text_hash CHAR(64) NOT NULL,
            stt_confidence NUMERIC(4, 3) NULL,
            transcript_may_be_inaccurate BOOLEAN NOT NULL DEFAULT FALSE,
            risk_type VARCHAR(40) NOT NULL,
            explanation_ko VARCHAR(1000) NOT NULL,
            alternative_expression_en VARCHAR(1000) NOT NULL,
            display_state VARCHAR(20) NOT NULL DEFAULT 'VISIBLE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dismissed_at TIMESTAMPTZ NULL,
            CONSTRAINT fk_speech_feedback_meeting FOREIGN KEY (meeting_id)
                REFERENCES meetings (id) ON DELETE CASCADE,
            CONSTRAINT fk_speech_feedback_participant FOREIGN KEY (participant_id)
                REFERENCES participants (id) ON DELETE CASCADE,
            CONSTRAINT ck_speech_feedback_detected_text
                CHECK (length(btrim(detected_text)) BETWEEN 1 AND 2000),
            CONSTRAINT ck_speech_feedback_text_hash
                CHECK (normalized_text_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_speech_feedback_confidence
                CHECK (stt_confidence IS NULL OR stt_confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_speech_feedback_risk_type CHECK (
                risk_type IN (
                    'DIRECT_REJECTION', 'PERSONAL_ATTACK', 'AMBIGUOUS_INTENT',
                    'IDIOM_OR_JOKE', 'PROFILE_CONFLICT', 'OTHER'
                )
            ),
            CONSTRAINT ck_speech_feedback_explanation
                CHECK (length(btrim(explanation_ko)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_speech_feedback_alternative
                CHECK (length(btrim(alternative_expression_en)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_speech_feedback_display_state
                CHECK (display_state IN ('VISIBLE', 'DISMISSED')),
            CONSTRAINT ck_speech_feedback_dismissed_at CHECK (
                (display_state = 'VISIBLE' AND dismissed_at IS NULL)
                OR (display_state = 'DISMISSED' AND dismissed_at IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_speech_feedback_meeting_created_at "
        "ON speech_feedback (meeting_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_speech_feedback_participant_created_at "
        "ON speech_feedback (participant_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_speech_feedback_duplicate_window "
        "ON speech_feedback (participant_id, normalized_text_hash, risk_type, created_at DESC)"
    )
    op.execute(
        "COMMENT ON TABLE speech_feedback IS "
        "'F-03에서 위험이 감지된 피드백만 저장. detected_text는 회의 종료 시 함께 삭제된다.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS speech_feedback")
    op.execute("DROP TABLE IF EXISTS pre_speech_requests")
