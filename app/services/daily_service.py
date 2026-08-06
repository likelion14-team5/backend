import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)
ROOM_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@dataclass(frozen=True, slots=True)
class DailyRoom:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class DailyMediaSession:
    token: str
    expires_at: datetime


class DailyService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self, error_code: str) -> dict[str, str]:
        api_key = self.settings.daily_api_key.get_secret_value()
        if not api_key:
            raise AppError(
                status_code=502,
                code=error_code,
                message="영상회의 서비스 설정을 확인할 수 없습니다.",
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        error_code: str,
        message: str,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self.settings.daily_api_base_url.rstrip("/"),
                timeout=self.settings.daily_request_timeout_seconds,
                headers=self._headers(error_code),
            ) as client:
                response = client.request(method, path, json=json)
                response.raise_for_status()
                return response
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            logger.warning(
                "Daily request failed operation=%s status=%s type=%s",
                error_code,
                status,
                type(exc).__name__,
            )
            raise AppError(status_code=502, code=error_code, message=message) from exc

    def create_room(self, max_participants: int) -> DailyRoom:
        room_name = f"meeting_{uuid4().hex}"
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.daily_room_ttl_minutes)
        response = self._request(
            "POST",
            "/rooms",
            error_code="DAILY_ROOM_CREATE_FAILED",
            message="영상회의 방을 생성하지 못했습니다.",
            json={
                "name": room_name,
                "privacy": "private",
                "properties": {
                    "exp": int(expires_at.timestamp()),
                    "eject_at_room_exp": True,
                    "max_participants": max_participants,
                    "enforce_unique_user_ids": True,
                    "enable_chat": False,
                },
            },
        )
        try:
            payload = response.json()
            returned_name = payload["name"]
            room_url = payload["url"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                status_code=502,
                code="DAILY_ROOM_CREATE_FAILED",
                message="영상회의 방 응답을 확인하지 못했습니다.",
            ) from exc
        if (
            not isinstance(returned_name, str)
            or not ROOM_NAME_PATTERN.fullmatch(returned_name)
            or not isinstance(room_url, str)
            or not room_url.startswith("https://")
            or urlparse(room_url).hostname != self.settings.daily_domain
        ):
            raise AppError(
                status_code=502,
                code="DAILY_ROOM_CREATE_FAILED",
                message="영상회의 방 응답을 확인하지 못했습니다.",
            )
        return DailyRoom(name=returned_name, url=room_url)

    def create_meeting_token(
        self,
        *,
        room_name: str,
        participant_id: UUID,
        display_name: str,
        is_owner: bool,
    ) -> DailyMediaSession:
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.daily_token_ttl_minutes)
        response = self._request(
            "POST",
            "/meeting-tokens",
            error_code="DAILY_TOKEN_CREATE_FAILED",
            message="영상회의 입장 정보를 발급하지 못했습니다.",
            json={
                "properties": {
                    "room_name": room_name,
                    "user_id": str(participant_id),
                    "user_name": display_name,
                    "is_owner": is_owner,
                    "exp": int(expires_at.timestamp()),
                    "eject_at_token_exp": True,
                }
            },
        )
        try:
            token = response.json()["token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                status_code=502,
                code="DAILY_TOKEN_CREATE_FAILED",
                message="영상회의 입장 정보를 확인하지 못했습니다.",
            ) from exc
        if not isinstance(token, str) or len(token) < 20:
            raise AppError(
                status_code=502,
                code="DAILY_TOKEN_CREATE_FAILED",
                message="영상회의 입장 정보를 확인하지 못했습니다.",
            )
        return DailyMediaSession(token=token, expires_at=expires_at)

    def delete_room(self, room_name: str) -> None:
        self._request(
            "DELETE",
            f"/rooms/{room_name}",
            error_code="DAILY_ROOM_UNAVAILABLE",
            message="영상회의 방을 종료하지 못했습니다.",
        )

    def delete_room_best_effort(self, room_name: str) -> None:
        try:
            self.delete_room(room_name)
        except AppError as exc:
            logger.warning("Daily room cleanup failed code=%s", exc.code)


def get_daily_service() -> DailyService:
    return DailyService()
