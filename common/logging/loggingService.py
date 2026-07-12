from __future__ import annotations

import json
import logging
from typing import Any


class LoggingService:
    sensitiveKeys = {
        "apiKey",
        "authorization",
        "token",
        "accessToken",
        "refreshToken",
        "linkToken",
        "password",
        "otp",
        "aadhaar",
        "mobile",
        "documentData",
        "content",
        "fhirJson",
    }

    def __init__(self, name: str) -> None:
        self.logger = self.getLogger(name)

    @staticmethod
    def getLogger(name: str) -> logging.Logger:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        return logging.getLogger(name)

    @classmethod
    def redactSensitive(cls, value: Any) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                if str(key).lower() in {k.lower() for k in cls.sensitiveKeys}:
                    output[str(key)] = "***redacted***"
                else:
                    output[str(key)] = cls.redactSensitive(item)
            return output
        if isinstance(value, list):
            return [cls.redactSensitive(item) for item in value]
        return value

    def logInput(
        self,
        operation: str,
        body: Any | None = None,
        headers: dict[str, Any] | None = None,
        hospitalId: str = "",
    ) -> None:
        safePayload = self.redactSensitive({"headers": headers or {}, "body": body or {}})
        text = json.dumps(safePayload, default=str, separators=(",", ":"))
        self.logger.info("input operation=%s hospitalId=%s payload=%s", operation, hospitalId, text[:4000])

    def logProcess(self, operation: str, message: str = "", **fields: Any) -> None:
        self.logger.info(
            "process operation=%s message=%s fields=%s",
            operation,
            message,
            json.dumps(fields, default=str, separators=(",", ":"))[:4000],
        )

    def logError(self, operation: str, error: Exception, **fields: Any) -> None:
        self.logger.exception("error operation=%s error=%s fields=%s", operation, error, json.dumps(fields, default=str))
