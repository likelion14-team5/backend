from typing import Any

from fastapi.testclient import TestClient


def profile(
    name: str, *, timezone: str | None = "Asia/Seoul", job_title: str = "Product Manager"
) -> dict[str, Any]:
    return {
        "display_name": name,
        "country_code": "KR",
        "organization": "Demo Labs",
        "job_title": job_title,
        "languages": ["Korean", "English"],
        "english_proficiency": "INTERMEDIATE",
        "communication_style": "BALANCED",
        "timezone": timezone,
        "additional_considerations": "Please explain acronyms briefly.",
    }


def create_meeting(
    client: TestClient,
    *,
    host_name: str = "Host",
    max_participants: int = 4,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/meetings",
        json={
            "title": "Global Release Sync",
            "max_participants": max_participants,
            "host_profile": profile(host_name),
            "profile_sharing_consent": True,
            "voice_analysis_consent": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def join_meeting(client: TestClient, meeting_id: str, name: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/meetings/{meeting_id}/participants",
        json={
            "profile": profile(name),
            "profile_sharing_consent": True,
            "voice_analysis_consent": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def token_header(token: str) -> dict[str, str]:
    return {"X-Participant-Token": token}
