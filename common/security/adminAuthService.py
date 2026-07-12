from __future__ import annotations

from typing import Any

from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.security.apiKeyAuthService import ApiKeyAuthService


class AdminAuthService:
    def __init__(self) -> None:
        self.settings = getSettings()

    def authenticate(self, headers: dict[str, Any]) -> None:
        token = ApiKeyAuthService.extractBearerToken(headers)
        adminKey = (self.settings.adminKey or "").strip()
        if not adminKey:
            raise AppError(503, ErrorCode.INTERNAL_ERROR, "Admin key not configured on this environment")
        if not token or token != adminKey:
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Valid admin key required")
