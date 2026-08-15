import os
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/meeting_mvp_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DAILY_API_KEY"] = "test-daily-api-key"
os.environ["FRONTEND_ORIGIN"] = "http://test.frontend"
os.environ["PUBLIC_APP_URL"] = "http://test.frontend"

from app.api.dependencies import get_db  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.ai import (  # noqa: E402
    PreSpeechRequest,
    PreSpeechResult,
    SpeechFeedbackRequest,
    SpeechFeedbackResult,
)
from app.services.ai_service import get_ai_service  # noqa: E402
from app.services.daily_service import (  # noqa: E402
    DailyMediaSession,
    DailyRoom,
    get_daily_service,
)

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@dataclass
class FakeDailyService:
    room_sequence: int = 0
    created_rooms: list[tuple[str, int]] = field(default_factory=list)
    token_requests: list[dict[str, object]] = field(default_factory=list)
    deleted_rooms: list[str] = field(default_factory=list)
    fail_room_creation: bool = False
    fail_token_creation: bool = False

    def create_room(self, max_participants: int) -> DailyRoom:
        if self.fail_room_creation:
            raise AppError(502, "DAILY_ROOM_CREATE_FAILED", "영상회의 방을 생성하지 못했습니다.")
        self.room_sequence += 1
        name = f"test_room_{self.room_sequence}"
        self.created_rooms.append((name, max_participants))
        return DailyRoom(name=name, url=f"https://test.daily.co/{name}")

    def create_meeting_token(
        self,
        *,
        room_name: str,
        participant_id: UUID,
        display_name: str,
        is_owner: bool,
    ) -> DailyMediaSession:
        if self.fail_token_creation:
            raise AppError(
                502, "DAILY_TOKEN_CREATE_FAILED", "영상회의 입장 정보를 발급하지 못했습니다."
            )
        self.token_requests.append(
            {
                "room_name": room_name,
                "participant_id": participant_id,
                "display_name": display_name,
                "is_owner": is_owner,
            }
        )
        return DailyMediaSession(
            token=f"daily-test-token-{participant_id}",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

    def delete_room_best_effort(self, room_name: str) -> None:
        self.deleted_rooms.append(room_name)


@dataclass
class FakeAiService:
    pre_speech_result: PreSpeechResult | None = None
    speech_feedback_result: SpeechFeedbackResult | None = None
    fail_pre_speech: bool = False
    fail_speech_feedback: bool = False
    pre_speech_calls: list[PreSpeechRequest] = field(default_factory=list)
    speech_feedback_calls: list[SpeechFeedbackRequest] = field(default_factory=list)

    def generate_pre_speech(self, request: PreSpeechRequest) -> PreSpeechResult:
        self.pre_speech_calls.append(request)
        if self.fail_pre_speech:
            raise AppError(502, "AI_PRE_SPEECH_FAILED", "AI 응답 생성에 실패했습니다.")
        return self.pre_speech_result or PreSpeechResult(
            expression="Given the timeline, could we revisit this?",
            reason="테스트용 기본 추천입니다.",
        )

    def generate_speech_feedback(self, request: SpeechFeedbackRequest) -> SpeechFeedbackResult:
        self.speech_feedback_calls.append(request)
        if self.fail_speech_feedback:
            raise AppError(502, "AI_SPEECH_FEEDBACK_FAILED", "AI 응답 생성에 실패했습니다.")
        if self.speech_feedback_result is not None:
            return self.speech_feedback_result
        return SpeechFeedbackResult(
            flagged=False,
            original_text=request.english_text,
            type=None,
            reason=None,
            alternative=None,
        )


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE participants, meetings CASCADE"))
    yield
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE participants, meetings CASCADE"))


@pytest.fixture
def fake_daily() -> FakeDailyService:
    return FakeDailyService()


@pytest.fixture
def fake_ai() -> FakeAiService:
    return FakeAiService()


@pytest.fixture
def client(
    fake_daily: FakeDailyService, fake_ai: FakeAiService
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_daily_service] = lambda: fake_daily
    app.dependency_overrides[get_ai_service] = lambda: fake_ai
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
