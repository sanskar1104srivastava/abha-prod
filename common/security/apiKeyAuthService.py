from __future__ import annotations

from typing import Any

from common.constants.errorCodes import ErrorCode
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.http.errorHandler import AppError
from common.utils.hashUtils import HashUtils


class ApiKeyAuthService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()

    def authenticate(self, headers: dict[str, Any]) -> dict[str, Any]:
        token = self.extractBearerToken(headers)
        if not token:
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Bearer API key is required")
        apiKeyHash = HashUtils.sha256Text(token)
        item = self.dbService.getItem(TableName.API_KEYS.value, {"apiKeyHash": apiKeyHash}, consistentRead=True)
        if not item or str(item.get("status") or "active").lower() != "active":
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Invalid or inactive API key")
        hospitalId = str(item.get("hospitalId") or "").strip()
        if not hospitalId:
            raise AppError(403, ErrorCode.FORBIDDEN, "API key is not mapped to a hospital")
        return {
            "hospitalId": hospitalId,
            "apiKeyHash": apiKeyHash,
            "hipId": str(item.get("hipId") or ""),
            "hiuId": str(item.get("hiuId") or ""),
            "environment": str(item.get("environment") or "sandbox"),
        }

    @staticmethod
    def extractBearerToken(headers: dict[str, Any]) -> str:
        lowered = {str(key).lower(): str(value) for key, value in headers.items()}
        value = lowered.get("authorization", "").strip()
        if value.lower().startswith("bearer "):
            return value.split(" ", 1)[1].strip()
        return ""
