"""Create meetings and participants tables.

Revision ID: 20260806_0001
Revises:
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE meetings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            max_participants SMALLINT NOT NULL DEFAULT 4,
            daily_room_name VARCHAR(128) NOT NULL UNIQUE,
            daily_room_url VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMPTZ NULL,
            CONSTRAINT ck_meetings_title_not_blank
                CHECK (length(btrim(title)) BETWEEN 1 AND 120),
            CONSTRAINT ck_meetings_status CHECK (status IN ('ACTIVE', 'ENDED')),
            CONSTRAINT ck_meetings_max_participants CHECK (max_participants BETWEEN 2 AND 4),
            CONSTRAINT ck_meetings_daily_room_name CHECK (
                length(btrim(daily_room_name)) BETWEEN 1 AND 128
                AND daily_room_name ~ '^[A-Za-z0-9_-]+$'
            ),
            CONSTRAINT ck_meetings_daily_room_url CHECK (
                length(btrim(daily_room_url)) BETWEEN 1 AND 255
                AND daily_room_url ~ '^https://'
            ),
            CONSTRAINT ck_meetings_ended_at CHECK (
                (status = 'ACTIVE' AND ended_at IS NULL)
                OR (status = 'ENDED' AND ended_at IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_meetings_status_created_at ON meetings (status, created_at DESC)")
    op.execute(
        "COMMENT ON TABLE meetings IS "
        "'회의 최소 메타데이터. 회의 종료 후에도 종료 상태 응답을 위해 유지한다.'"
    )
    op.execute(
        "COMMENT ON COLUMN meetings.daily_room_name IS "
        "'Daily private room name. public meeting API에는 반환하지 않는다.'"
    )
    op.execute(
        "COMMENT ON COLUMN meetings.daily_room_url IS "
        "'Daily private room URL. 참가자 검증 후 media-session API에서만 반환한다.'"
    )
    op.execute(
        """
        CREATE TABLE participants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL,
            participant_token_hash CHAR(64) NOT NULL UNIQUE,
            role VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
            status VARCHAR(20) NOT NULL DEFAULT 'JOINED',
            display_name VARCHAR(50) NOT NULL,
            country_code CHAR(2) NOT NULL,
            organization VARCHAR(100) NOT NULL,
            job_title VARCHAR(100) NOT NULL,
            languages TEXT[] NOT NULL,
            english_proficiency VARCHAR(20) NOT NULL,
            communication_style VARCHAR(30) NOT NULL,
            timezone VARCHAR(64) NULL,
            additional_considerations VARCHAR(500) NULL,
            profile_sharing_consent BOOLEAN NOT NULL,
            profile_consent_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            voice_analysis_consent BOOLEAN NOT NULL DEFAULT FALSE,
            voice_consent_at TIMESTAMPTZ NULL,
            voice_analysis_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            left_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_participants_meeting FOREIGN KEY (meeting_id)
                REFERENCES meetings (id) ON DELETE CASCADE,
            CONSTRAINT ck_participants_token_hash
                CHECK (participant_token_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_participants_role CHECK (role IN ('HOST', 'MEMBER')),
            CONSTRAINT ck_participants_status CHECK (status IN ('JOINED', 'LEFT')),
            CONSTRAINT ck_participants_display_name
                CHECK (length(btrim(display_name)) BETWEEN 1 AND 50),
            CONSTRAINT ck_participants_country_code CHECK (country_code ~ '^[A-Z]{2}$'),
            CONSTRAINT ck_participants_organization
                CHECK (length(btrim(organization)) BETWEEN 1 AND 100),
            CONSTRAINT ck_participants_job_title
                CHECK (length(btrim(job_title)) BETWEEN 1 AND 100),
            CONSTRAINT ck_participants_languages CHECK (cardinality(languages) BETWEEN 1 AND 10),
            CONSTRAINT ck_participants_english_proficiency
                CHECK (english_proficiency IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')),
            CONSTRAINT ck_participants_communication_style CHECK (
                communication_style IN (
                    'DIRECT', 'INDIRECT', 'FACT_FOCUSED', 'EMOTION_EXPRESSIVE', 'BALANCED'
                )
            ),
            CONSTRAINT ck_participants_timezone CHECK (
                timezone IS NULL OR length(btrim(timezone)) BETWEEN 1 AND 64
            ),
            CONSTRAINT ck_participants_additional_considerations CHECK (
                additional_considerations IS NULL
                OR length(btrim(additional_considerations)) BETWEEN 1 AND 500
            ),
            CONSTRAINT ck_participants_profile_consent CHECK (profile_sharing_consent = TRUE),
            CONSTRAINT ck_participants_voice_consent_at CHECK (
                (voice_analysis_consent = TRUE AND voice_consent_at IS NOT NULL)
                OR (voice_analysis_consent = FALSE AND voice_consent_at IS NULL)
            ),
            CONSTRAINT ck_participants_voice_enabled CHECK (
                voice_analysis_enabled = FALSE OR voice_analysis_consent = TRUE
            ),
            CONSTRAINT ck_participants_left_at CHECK (
                (status = 'JOINED' AND left_at IS NULL)
                OR (status = 'LEFT' AND left_at IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_participants_meeting_status ON participants (meeting_id, status)")
    op.execute(
        "CREATE INDEX ix_participants_meeting_joined_at ON participants (meeting_id, joined_at)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_participants_joined_display_name
        ON participants (meeting_id, lower(display_name))
        WHERE status = 'JOINED'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_participants_one_host_per_meeting
        ON participants (meeting_id)
        WHERE role = 'HOST'
        """
    )
    op.execute(
        "COMMENT ON TABLE participants IS "
        "'계정이 아닌 회의 세션 참가자와 공개 프로필. 회의 종료 시 삭제한다.'"
    )
    op.execute(
        "COMMENT ON COLUMN participants.participant_token_hash IS "
        "'클라이언트에 한 번 발급한 opaque token의 SHA-256 hex digest.'"
    )
    op.execute(
        "COMMENT ON COLUMN participants.languages IS "
        "'주요 사용 언어. 순서상 첫 항목을 UI의 대표 언어로 사용한다.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS participants")
    op.execute("DROP TABLE IF EXISTS meetings")
