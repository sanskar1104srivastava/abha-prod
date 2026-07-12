from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.constants.errorCodes import ErrorCode


class AppError(Exception):
    def __init__(
        self,
        statusCode: int,
        errorCode: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.statusCode = statusCode
        self.errorCode = errorCode
        self.message = message
        self.details = details or {}
        super().__init__(message)


def addErrorHandlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handleAppError(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.statusCode,
            content={
                "errorCode": exc.errorCode.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def handleUnhandledError(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "errorCode": ErrorCode.INTERNAL_ERROR.value,
                "message": "Internal server error",
                "details": {"type": exc.__class__.__name__},
            },
        )
