from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.models.participant import Participant
from app.security.participant_token import hash_participant_token
from tests.conftest import FakeDailyService
from tests.helpers import create_meeting, join_meeting, profile, token_header


def test_complete_video_meeting_backend_lifecycle(
    client: TestClient,
    db: Session,
    fake_daily: FakeDailyService,
) -> None:
    created = create_meeting(client, host_name="Jiwon", max_participants=4)
    meeting_id = created["meeting"]["id"]
    host_id = created["participant"]["id"]
    host_token = created["participant_token"]

    assert created["share_url"] == f"http://test.frontend/join/{meeting_id}"
    assert created["meeting"]["current_participants"] == 1
    assert fake_daily.created_rooms == [("test_room_1", 4)]

    public = client.get(f"/api/v1/meetings/{meeting_id}/public")
    assert public.status_code == 200
    assert public.json()["data"] == {
        "id": meeting_id,
        "title": "Global Release Sync",
        "status": "ACTIVE",
        "max_participants": 4,
        "current_participants": 1,
        "can_join": True,
    }
    assert "room" not in public.text
    assert "Jiwon" not in public.text

    missing_token = client.get(f"/api/v1/meetings/{meeting_id}")
    assert missing_token.status_code == 401
    assert missing_token.json()["error"]["code"] == "INVALID_PARTICIPANT_TOKEN"
    UUID(missing_token.json()["request_id"])

    joined = join_meeting(client, meeting_id, "Alex")
    member_id = joined["participant"]["id"]
    member_token = joined["participant_token"]

    context = client.get(f"/api/v1/meetings/{meeting_id}", headers=token_header(host_token))
    assert context.status_code == 200
    assert context.json()["data"]["meeting"]["current_participants"] == 2
    assert context.json()["data"]["video"] == {
        "provider": "DAILY",
        "room_name": "test_room_1",
    }

    host_media = client.post(
        f"/api/v1/meetings/{meeting_id}/media-session",
        headers=token_header(host_token),
    )
    member_media = client.post(
        f"/api/v1/meetings/{meeting_id}/media-session",
        headers=token_header(member_token),
    )
    assert host_media.status_code == member_media.status_code == 200
    assert host_media.json()["data"]["room_url"] == "https://test.daily.co/test_room_1"
    assert fake_daily.token_requests[0]["is_owner"] is True
    assert fake_daily.token_requests[1]["is_owner"] is False
    assert fake_daily.token_requests[0]["participant_id"] == UUID(host_id)
    assert fake_daily.token_requests[1]["participant_id"] == UUID(member_id)

    participants = client.get(
        f"/api/v1/meetings/{meeting_id}/participants",
        headers=token_header(host_token),
    )
    assert participants.status_code == 200
    assert participants.json()["meta"] == {"count": 2}
    assert {item["display_name"] for item in participants.json()["data"]} == {
        "Jiwon",
        "Alex",
    }
    assert all(item["local_time"] for item in participants.json()["data"])

    detail = client.get(
        f"/api/v1/meetings/{meeting_id}/participants/{member_id}",
        headers=token_header(host_token),
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["profile"]["display_name"] == "Alex"

    updated = client.patch(
        f"/api/v1/meetings/{meeting_id}/participants/me/profile",
        headers=token_header(member_token),
        json={"job_title": "Backend Engineer", "timezone": "America/New_York"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["profile"]["job_title"] == "Backend Engineer"

    forbidden_end = client.post(
        f"/api/v1/meetings/{meeting_id}/end",
        headers=token_header(member_token),
    )
    assert forbidden_end.status_code == 403
    assert forbidden_end.json()["error"]["code"] == "HOST_REQUIRED"

    left = client.post(
        f"/api/v1/meetings/{meeting_id}/leave",
        headers=token_header(member_token),
    )
    assert left.status_code == 204
    assert left.content == b""

    after_leave = client.get(
        f"/api/v1/meetings/{meeting_id}/participants",
        headers=token_header(host_token),
    )
    assert after_leave.json()["meta"] == {"count": 1}

    ended = client.post(
        f"/api/v1/meetings/{meeting_id}/end",
        headers=token_header(host_token),
    )
    assert ended.status_code == 204
    assert fake_daily.deleted_rooms == ["test_room_1"]
    db.expire_all()
    assert db.scalar(select(func.count(Participant.id))) == 0
    meeting = db.get(Meeting, UUID(meeting_id))
    assert meeting is not None
    assert meeting.status == "ENDED"
    assert meeting.ended_at is not None

    public_after_end = client.get(f"/api/v1/meetings/{meeting_id}/public")
    assert public_after_end.status_code == 200
    assert public_after_end.json()["data"]["can_join"] is False
    assert public_after_end.json()["data"]["current_participants"] == 0

    polling_after_end = client.get(
        f"/api/v1/meetings/{meeting_id}/participants",
        headers=token_header(host_token),
    )
    assert polling_after_end.status_code == 409
    assert polling_after_end.json()["error"]["code"] == "MEETING_ENDED"


def test_raw_participant_token_is_never_stored(client: TestClient, db: Session) -> None:
    created = create_meeting(client)
    raw_token = created["participant_token"]

    participant = db.scalar(select(Participant))

    assert participant is not None
    assert participant.participant_token_hash != raw_token
    assert participant.participant_token_hash == hash_participant_token(raw_token)


def test_duplicate_name_and_capacity_are_rejected(client: TestClient) -> None:
    created = create_meeting(client, host_name="SameName", max_participants=2)
    meeting_id = created["meeting"]["id"]

    duplicate = client.post(
        f"/api/v1/meetings/{meeting_id}/participants",
        json={
            "profile": profile("samename"),
            "profile_sharing_consent": True,
            "voice_analysis_consent": False,
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DISPLAY_NAME_TAKEN"

    join_meeting(client, meeting_id, "Second")
    full = client.post(
        f"/api/v1/meetings/{meeting_id}/participants",
        json={
            "profile": profile("Third"),
            "profile_sharing_consent": True,
            "voice_analysis_consent": False,
        },
    )
    assert full.status_code == 409
    assert full.json()["error"]["code"] == "MEETING_FULL"


def test_concurrent_joins_cannot_exceed_capacity(client: TestClient) -> None:
    created = create_meeting(client, max_participants=2)
    meeting_id = created["meeting"]["id"]

    def attempt(name: str) -> tuple[int, str | None]:
        response = client.post(
            f"/api/v1/meetings/{meeting_id}/participants",
            json={
                "profile": profile(name),
                "profile_sharing_consent": True,
                "voice_analysis_consent": False,
            },
        )
        body = response.json()
        return response.status_code, body.get("error", {}).get("code")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ["Alpha", "Beta"]))

    assert sorted(status for status, _ in results) == [201, 409]
    assert {code for _, code in results} == {None, "MEETING_FULL"}


def test_token_cannot_cross_meeting_boundary(client: TestClient) -> None:
    first = create_meeting(client, host_name="First")
    second = create_meeting(client, host_name="Second")

    response = client.get(
        f"/api/v1/meetings/{second['meeting']['id']}/participants",
        headers=token_header(first["participant_token"]),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_PARTICIPANT_TOKEN"


def test_validation_errors_follow_common_envelope(client: TestClient) -> None:
    response = client.post(
        "/api/v1/meetings",
        json={
            "title": " ",
            "max_participants": 5,
            "host_profile": profile("Host"),
            "profile_sharing_consent": False,
            "voice_analysis_consent": False,
            "unexpected": "rejected",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["field_errors"]
    UUID(body["request_id"])


def test_daily_room_failure_does_not_create_database_rows(
    client: TestClient,
    db: Session,
    fake_daily: FakeDailyService,
) -> None:
    fake_daily.fail_room_creation = True

    response = client.post(
        "/api/v1/meetings",
        json={
            "title": "Unavailable room",
            "max_participants": 4,
            "host_profile": profile("Host"),
            "profile_sharing_consent": True,
            "voice_analysis_consent": False,
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "DAILY_ROOM_CREATE_FAILED"
    assert db.scalar(select(func.count(Meeting.id))) == 0
    assert db.scalar(select(func.count(Participant.id))) == 0


def test_daily_token_failure_only_blocks_video_area(
    client: TestClient,
    fake_daily: FakeDailyService,
) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    headers = token_header(created["participant_token"])
    fake_daily.fail_token_creation = True

    media = client.post(
        f"/api/v1/meetings/{meeting_id}/media-session",
        headers=headers,
    )
    participants = client.get(
        f"/api/v1/meetings/{meeting_id}/participants",
        headers=headers,
    )

    assert media.status_code == 502
    assert media.json()["error"]["code"] == "DAILY_TOKEN_CREATE_FAILED"
    assert participants.status_code == 200
    assert participants.json()["meta"] == {"count": 1}
