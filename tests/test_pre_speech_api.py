from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.pre_speech_request import PreSpeechRequest
from tests.conftest import FakeAiService
from tests.helpers import create_meeting, join_meeting, token_header


def _row_count(db: Session) -> int:
    return int(db.scalar(select(func.count(PreSpeechRequest.id))) or 0)


def test_create_pre_speech_saves_to_db(
    client: TestClient, db: Session, fake_ai: FakeAiService
) -> None:
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    host_id = created["participant"]["id"]
    host_token = created["participant_token"]
    member = join_meeting(client, meeting_id, "Alex")
    member_id = member["participant"]["id"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={
            "input_ko": "이 일정은 솔직히 어려울 것 같아요",
            "target_participant_id": member_id,
            "meeting_context": "일정 조율 회의",
        },
        headers=token_header(host_token),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["input_ko"] == "이 일정은 솔직히 어려울 것 같아요"
    assert data["target_participant_id"] == member_id
    assert data["recommended_expression_en"] == "Given the timeline, could we revisit this?"
    assert data["parent_request_id"] is None
    assert _row_count(db) == 1

    call = fake_ai.pre_speech_calls[0]
    assert call.counterpart_profile.proficiency == "중급"
    assert call.counterpart_profile.communication_style == "균형적"
    assert call.counterpart_profile.job_role == "Product Manager"

    db.expunge_all()
    saved = db.get(PreSpeechRequest, data["id"])
    assert saved is not None
    assert saved.requester_participant_id == UUID(host_id)


def test_create_pre_speech_without_target_uses_neutral_profile(
    client: TestClient, fake_ai: FakeAiService
) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    token = created["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요"},
        headers=token_header(token),
    )
    assert response.status_code == 201, response.text
    call = fake_ai.pre_speech_calls[0]
    assert call.counterpart_profile.job_role == "회의 참가자"


def test_create_pre_speech_self_target_rejected(client: TestClient) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    host_id = created["participant"]["id"]
    token = created["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요", "target_participant_id": host_id},
        headers=token_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SELF_TARGET_NOT_ALLOWED"


def test_create_pre_speech_target_not_in_meeting(client: TestClient) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    token = created["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요", "target_participant_id": str(uuid4())},
        headers=token_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TARGET_PARTICIPANT_NOT_FOUND"


def test_regenerate_links_parent(client: TestClient, db: Session) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    token = created["participant_token"]

    first = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요"},
        headers=token_header(token),
    ).json()["data"]

    regenerated = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech/{first['id']}/regenerate",
        headers=token_header(token),
    )
    assert regenerated.status_code == 201, regenerated.text
    data = regenerated.json()["data"]
    assert data["parent_request_id"] == first["id"]
    assert data["id"] != first["id"]
    assert _row_count(db) == 2


def test_get_pre_speech_ownership(client: TestClient) -> None:
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    host_token = created["participant_token"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    own = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요"},
        headers=token_header(host_token),
    ).json()["data"]

    as_owner = client.get(
        f"/api/v1/meetings/{meeting_id}/pre-speech/{own['id']}",
        headers=token_header(host_token),
    )
    assert as_owner.status_code == 200

    as_other = client.get(
        f"/api/v1/meetings/{meeting_id}/pre-speech/{own['id']}",
        headers=token_header(member_token),
    )
    assert as_other.status_code == 404
    assert as_other.json()["error"]["code"] == "PRE_SPEECH_NOT_FOUND"


def test_create_pre_speech_requires_token(client: TestClient) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_PARTICIPANT_TOKEN"


def test_create_pre_speech_ai_failure_not_saved(
    client: TestClient, db: Session, fake_ai: FakeAiService
) -> None:
    fake_ai.fail_pre_speech = True
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    token = created["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/pre-speech",
        json={"input_ko": "안녕하세요"},
        headers=token_header(token),
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_PRE_SPEECH_FAILED"
    assert _row_count(db) == 0
