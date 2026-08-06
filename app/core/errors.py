import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppError(Exception):
    status_code: int
    code: str
    message: str
    field_errors: list[dict[str, str]] | None = None


def request_id_for(request: Request) -> UUID:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, UUID):
        return request_id
    request_id = uuid4()
    request.state.request_id = request_id
    return request_id


def error_payload(
    *,
    request_id: UUID,
    code: str,
    message: str,
    field_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors,
        },
        "request_id": str(request_id),
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                request_id=request_id_for(request),
                code=exc.code,
                message=exc.message,
                field_errors=exc.field_errors,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors: list[dict[str, str]] = []
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part not in {"body", "path", "query"}]
            field_errors.append(
                {
                    "field": ".".join(location) or "request",
                    "message": str(error["msg"]),
                }
            )
        return JSONResponse(
            status_code=422,
            content=error_payload(
                request_id=request_id_for(request),
                code="VALIDATION_ERROR",
                message="요청 값을 확인해주세요.",
                field_errors=field_errors,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_for(request)
        logger.error(
            "Unhandled server error request_id=%s type=%s",
            request_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                request_id=request_id,
                code="INTERNAL_ERROR",
                message="서버 내부 오류가 발생했습니다.",
            ),
        )
