from __future__ import annotations

from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError


class ValidationUtils:
    @staticmethod
    def requireNonEmpty(value: str, fieldName: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise AppError(422, ErrorCode.INVALID_REQUEST, f"{fieldName} is required")
        return text
