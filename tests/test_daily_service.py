import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.services.daily_service import DailyService


def daily_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused",
        daily_api_key=SecretStr("daily-secret"),
        daily_api_base_url="https://api.daily.test/v1",
        daily_domain="team.daily.co",
        daily_room_ttl_minutes=180,
        daily_token_ttl_minutes=120,
    )


@respx.mock
def test_create_private_daily_room_uses_security_properties() -> None:
    route = respx.post("https://api.daily.test/v1/rooms").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "meeting_returned",
                "url": "https://team.daily.co/meeting_returned",
            },
        )
    )

    room = DailyService(daily_settings()).create_room(4)

    request_body = json.loads(route.calls[0].request.content)
    assert room.name == "meeting_returned"
    assert request_body["privacy"] == "private"
    assert request_body["properties"]["max_participants"] == 4
    assert request_body["properties"]["enforce_unique_user_ids"] is True
    assert request_body["properties"]["eject_at_room_exp"] is True
    assert request_body["properties"]["enable_chat"] is False
    assert isinstance(request_body["properties"]["exp"], int)


@respx.mock
def test_create_daily_token_is_scoped_to_room_and_participant() -> None:
    route = respx.post("https://api.daily.test/v1/meeting-tokens").mock(
        return_value=httpx.Response(200, json={"token": "x" * 80})
    )
    participant_id = uuid4()

    result = DailyService(daily_settings()).create_meeting_token(
        room_name="meeting_123",
        participant_id=participant_id,
        display_name="Jiwon",
        is_owner=True,
    )

    properties = json.loads(route.calls[0].request.content)["properties"]
    assert properties["room_name"] == "meeting_123"
    assert properties["user_id"] == str(participant_id)
    assert properties["user_name"] == "Jiwon"
    assert properties["is_owner"] is True
    assert properties["eject_at_token_exp"] is True
    assert result.expires_at > datetime.now(UTC)


@respx.mock
def test_daily_failure_becomes_sanitized_api_error() -> None:
    respx.post("https://api.daily.test/v1/rooms").mock(
        return_value=httpx.Response(503, json={"sensitive": "provider detail"})
    )

    with pytest.raises(AppError) as raised:
        DailyService(daily_settings()).create_room(4)

    assert raised.value.status_code == 502
    assert raised.value.code == "DAILY_ROOM_CREATE_FAILED"
    assert "sensitive" not in raised.value.message


@respx.mock
def test_daily_room_cleanup_is_best_effort() -> None:
    respx.delete("https://api.daily.test/v1/rooms/meeting_123").mock(
        return_value=httpx.Response(503)
    )

    DailyService(daily_settings()).delete_room_best_effort("meeting_123")
