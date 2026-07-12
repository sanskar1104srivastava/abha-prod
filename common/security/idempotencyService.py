from __future__ import annotations

from typing import Any

from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.http.errorHandler import AppError
from common.utils.dateTimeUtils import DateTimeUtils
from common.utils.hashUtils import HashUtils


class IdempotencyService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()
        self.settings = getSettings()

    def requireKey(self, idempotencyKey: str | None) -> str:
        key = str(idempotencyKey or "").strip()
        if not key:
            raise AppError(400, ErrorCode.IDEMPOTENCY_KEY_REQUIRED, "Idempotency-Key header is required")
        return key

    def replayOrReserve(
        self,
        hospitalId: str,
        idempotencyKey: str,
        requestPayload: dict[str, Any],
    ) -> dict[str, Any] | None:
        requestHash = HashUtils.sha256Json(requestPayload)
        key = {"pk": f"HOSP#{hospitalId}", "sk": f"IDEMP#{idempotencyKey}"}
        existing = self.dbService.getItem(TableName.REQUEST_LOG.value, key, consistentRead=True)
        if existing:
            if existing.get("requestHash") != requestHash:
                raise AppError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "Idempotency key was already used with a different request")
            return existing.get("response") if isinstance(existing.get("response"), dict) else None
        self.dbService.putItem(
            TableName.REQUEST_LOG.value,
            {
                **key,
                "requestHash": requestHash,
                "recordType": "idempotency",
                "createdAt": DateTimeUtils.utcnowIso(),
                "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
            },
        )
        return None

    def storeResponse(self, hospitalId: str, idempotencyKey: str, response: dict[str, Any]) -> None:
        self.dbService.updateItem(
            TableName.REQUEST_LOG.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"IDEMP#{idempotencyKey}"},
            "SET #response = :response, updatedAt = :updatedAt",
            {":response": response, ":updatedAt": DateTimeUtils.utcnowIso()},
            {"#response": "response"},
        )
