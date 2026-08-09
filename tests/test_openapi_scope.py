from app.main import app

MEETING_SCOPE_OPERATIONS = {
    "/meetings": {"post": "createMeeting"},
    "/meetings/{meeting_id}/public": {"get": "getPublicMeeting"},
    "/meetings/{meeting_id}": {"get": "getMeetingContext"},
    "/meetings/{meeting_id}/media-session": {"post": "createMediaSession"},
    "/meetings/{meeting_id}/participants": {
        "post": "joinMeeting",
        "get": "listParticipants",
    },
    "/meetings/{meeting_id}/participants/{participant_id}": {"get": "getParticipantProfile"},
    "/meetings/{meeting_id}/participants/me/profile": {"patch": "updateMyProfile"},
    "/meetings/{meeting_id}/leave": {"post": "leaveMeeting"},
    "/meetings/{meeting_id}/end": {"post": "endMeeting"},
}

AI_SCOPE_OPERATIONS = {
    "/ai/pre-speech": {"post": "generatePreSpeech"},
    "/ai/speech-feedback": {"post": "generateSpeechFeedback"},
}


def test_implemented_operations_match_supplied_contract() -> None:
    generated = app.openapi()

    for path, methods in MEETING_SCOPE_OPERATIONS.items():
        generated_path = f"/api/v1{path}"
        assert generated_path in generated["paths"]
        for method, operation_id in methods.items():
            assert generated["paths"][generated_path][method]["operationId"] == operation_id

    assert generated["components"]["securitySchemes"]["ParticipantToken"] == {
        "type": "apiKey",
        "description": "회의 생성 또는 입장 성공 시 한 번 발급되는 회의 범위 opaque token",
        "in": "header",
        "name": "X-Participant-Token",
    }


def test_ai_operations_match_current_direct_scope() -> None:
    generated = app.openapi()

    for path, methods in AI_SCOPE_OPERATIONS.items():
        generated_path = f"/api/v1{path}"
        assert generated_path in generated["paths"]
        for method, operation_id in methods.items():
            assert generated["paths"][generated_path][method]["operationId"] == operation_id


def test_voice_analysis_route_is_not_in_current_backend_scope() -> None:
    generated_paths = set(app.openapi()["paths"])

    assert not any("voice-analysis" in path for path in generated_paths)
