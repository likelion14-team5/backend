import hashlib
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParticipantToken:
    raw: str
    digest: str


def hash_participant_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_participant_token() -> ParticipantToken:
    raw_token = secrets.token_urlsafe(32)
    return ParticipantToken(raw=raw_token, digest=hash_participant_token(raw_token))
