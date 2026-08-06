from app.security.participant_token import create_participant_token, hash_participant_token


def test_participant_token_is_opaque_and_only_hash_is_reproducible() -> None:
    token = create_participant_token()

    assert len(token.raw) >= 32
    assert len(token.digest) == 64
    assert token.raw != token.digest
    assert hash_participant_token(token.raw) == token.digest
