"""Einheitliche Fehlerbehandlung.

Alle erwarteten Fehler werden als ApiError geworfen und zu einer konsistenten
JSON-Form {"error": {"code", "message", "details"}} serialisiert. Das Frontend
kann sich darauf verlassen (typisierter ApiError).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


# Bequeme Konstruktoren fuer haeufige Faelle
def unauthorized(message: str = "Nicht authentifiziert", code: str = "unauthorized") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, code, message)


def forbidden(message: str = "Kein Zugriff", code: str = "forbidden") -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, code, message)


def not_found(message: str = "Nicht gefunden", code: str = "not_found") -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, code, message)


def bad_request(message: str, code: str = "bad_request", details: Any = None) -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, code, message, details)


def conflict(message: str, code: str = "conflict") -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "validation_error", "Eingabe ungueltig", jsonable_encoder(exc.errors())
            ),
        )
