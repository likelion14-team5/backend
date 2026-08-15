from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.speech_feedback import SpeechFeedback
from app.schemas.ai import SpeechFeedbackResult
from tests.conftest import FakeAiService
from tests.helpers import create_meeting, join_meeting, profile, token_header


def _row_count(db: Session) -> int:
    return int(db.scalar(select(func.count(SpeechFeedback.id))) or 0)


FLAGGED_RESULT = SpeechFeedbackResult(
    flagged=True,
    original_text="That schedule is impossible.",
    type="직접적 거절",
    reason="완곡한 소통을 선호하는 상대에게는 단정적으로 들릴 수 있어요.",
    alternative="I'm a little concerned this schedule might be hard to hit.",
)


def test_analyze_saves_when_risk_detected(
    client: TestClient, db: Session, fake_ai: FakeAiService
) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={
            "transcript": "That schedule is impossible.",
            "stt_confidence": 0.95,
            "stt_source": "WEB_SPEECH",
        },
        headers=token_header(member_token),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["risk_detected"] is True
    assert data["suppressed_duplicate"] is False
    assert data["feedback"]["risk_type"] == "DIRECT_REJECTION"
    assert data["feedback"]["display_state"] == "VISIBLE"
    assert _row_count(db) == 1

    call = fake_ai.speech_feedback_calls[0]
    assert call.counterpart_profile.job_role == "Product Manager"


def test_analyze_not_saved_when_no_risk(
    client: TestClient, db: Session
) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "Could you share the file when you get a chance?"},
        headers=token_header(member_token),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["risk_detected"] is False
    assert data["feedback"] is None
    assert _row_count(db) == 0


def test_analyze_requires_consent(client: TestClient) -> None:
    created = create_meeting(client)  # host joins with voice_analysis_consent=False
    meeting_id = created["meeting"]["id"]
    token = created["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "That schedule is impossible."},
        headers=token_header(token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "VOICE_CONSENT_REQUIRED"


def test_analyze_uses_specified_target_over_auto_pick(
    client: TestClient, fake_ai: FakeAiService
) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client, host_name="Jiwon")  # 자동 선택 시 host가 먼저 선택됨
    meeting_id = created["meeting"]["id"]

    casey_response = client.post(
        f"/api/v1/meetings/{meeting_id}/participants",
        json={
            "profile": profile("Casey", job_title="Data Analyst"),
            "profile_sharing_consent": True,
            "voice_analysis_consent": True,
        },
    )
    assert casey_response.status_code == 201, casey_response.text
    casey = casey_response.json()["data"]
    alex = join_meeting(client, meeting_id, "Alex")

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={
            "transcript": "That schedule is impossible.",
            "target_participant_id": casey["participant"]["id"],
        },
        headers=token_header(alex["participant_token"]),
    )

    assert response.status_code == 201, response.text
    call = fake_ai.speech_feedback_calls[-1]
    assert call.counterpart_profile.job_role == "Data Analyst"


def test_analyze_falls_back_to_auto_pick_without_target(
    client: TestClient, fake_ai: FakeAiService
) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    client.post(
        f"/api/v1/meetings/{meeting_id}/participants",
        json={
            "profile": profile("Casey", job_title="Data Analyst"),
            "profile_sharing_consent": True,
            "voice_analysis_consent": True,
        },
    )
    member = join_meeting(client, meeting_id, "Alex")

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "That schedule is impossible."},
        headers=token_header(member["participant_token"]),
    )

    assert response.status_code == 201, response.text
    call = fake_ai.speech_feedback_calls[-1]
    # target_participant_id 미지정 시 가장 먼저 입장한 다른 참가자(host)를 사용한다.
    assert call.counterpart_profile.job_role == "Product Manager"


def test_analyze_blocks_self_target(client: TestClient) -> None:
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    member = join_meeting(client, meeting_id, "Alex")

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={
            "transcript": "That schedule is impossible.",
            "target_participant_id": member["participant"]["id"],
        },
        headers=token_header(member["participant_token"]),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TARGET_NOT_IN_MEETING"


def test_analyze_blocks_target_from_other_meeting(client: TestClient) -> None:
    first = create_meeting(client, host_name="First")
    second = create_meeting(client, host_name="Second")
    member = join_meeting(client, first["meeting"]["id"], "Alex")

    response = client.post(
        f"/api/v1/meetings/{first['meeting']['id']}/speech-feedback/analyze",
        json={
            "transcript": "That schedule is impossible.",
            "target_participant_id": second["participant"]["id"],
        },
        headers=token_header(member["participant_token"]),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TARGET_NOT_IN_MEETING"


def test_analyze_duplicate_suppressed_within_30s(
    client: TestClient, db: Session, fake_ai: FakeAiService
) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]
    payload = {"transcript": "That schedule is impossible."}

    first = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json=payload,
        headers=token_header(member_token),
    )
    assert first.json()["data"]["suppressed_duplicate"] is False

    second = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json=payload,
        headers=token_header(member_token),
    )
    assert second.status_code == 201
    assert second.json()["data"]["suppressed_duplicate"] is True
    assert second.json()["data"]["risk_detected"] is True
    assert _row_count(db) == 1


def test_list_returns_only_own(client: TestClient, fake_ai: FakeAiService) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    host_token = created["participant_token"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "That schedule is impossible."},
        headers=token_header(member_token),
    )

    member_list = client.get(
        f"/api/v1/meetings/{meeting_id}/speech-feedback", headers=token_header(member_token)
    )
    assert member_list.json()["meta"]["count"] == 1

    host_list = client.get(
        f"/api/v1/meetings/{meeting_id}/speech-feedback", headers=token_header(host_token)
    )
    assert host_list.json()["meta"]["count"] == 0


def test_dismiss_updates_state_and_ownership(
    client: TestClient, fake_ai: FakeAiService
) -> None:
    fake_ai.speech_feedback_result = FLAGGED_RESULT
    created = create_meeting(client, host_name="Jiwon")
    meeting_id = created["meeting"]["id"]
    host_token = created["participant_token"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    saved = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "That schedule is impossible."},
        headers=token_header(member_token),
    ).json()["data"]["feedback"]

    other_attempt = client.patch(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/{saved['id']}",
        json={"display_state": "DISMISSED"},
        headers=token_header(host_token),
    )
    assert other_attempt.status_code == 404
    assert other_attempt.json()["error"]["code"] == "FEEDBACK_NOT_FOUND"

    dismissed = client.patch(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/{saved['id']}",
        json={"display_state": "DISMISSED"},
        headers=token_header(member_token),
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["data"]["display_state"] == "DISMISSED"
    assert dismissed.json()["data"]["dismissed_at"] is not None


def test_analyze_ai_failure_returns_502(
    client: TestClient, db: Session, fake_ai: FakeAiService
) -> None:
    fake_ai.fail_speech_feedback = True
    created = create_meeting(client)
    meeting_id = created["meeting"]["id"]
    member = join_meeting(client, meeting_id, "Alex")
    member_token = member["participant_token"]

    response = client.post(
        f"/api/v1/meetings/{meeting_id}/speech-feedback/analyze",
        json={"transcript": "That schedule is impossible."},
        headers=token_header(member_token),
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_SPEECH_FEEDBACK_FAILED"
    assert _row_count(db) == 0
