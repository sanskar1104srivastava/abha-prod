from __future__ import annotations

from typing import Any

from common.abdm.abdmCryptoService import AbdmCryptoService
from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class CallbackRouterDbService:
    def __init__(self, dbService: DynamoDbService | None = None, awsService: AwsService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()
        self.awsService = awsService or AwsService()
        self.settings = getSettings()

    def storeRawCallback(
        self,
        path: str,
        headers: dict[str, Any],
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        matchedRequest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        callbackId = AbdmCryptoService.newEventId()
        hospitalId = str((matchedRequest or {}).get("hospitalId") or "unmatched")
        trackingId = str((matchedRequest or {}).get("trackingId") or "")
        now = DateTimeUtils.utcnowIso()
        s3Key = f"callbacks/{DateTimeUtils.utcDatePath()}/{callbackId}.json"
        storedPayload: dict[str, Any] | None = payload
        if self.settings.callbackBodyBucket:
            self.awsService.putJsonObject(
                self.settings.callbackBodyBucket,
                s3Key,
                {
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                    "correlationIds": correlationIds,
                    "receivedAt": now,
                },
            )
            storedPayload = None
        item = {
            "pk": f"HOSP#{hospitalId}" if hospitalId != "unmatched" else "UNMATCHED",
            "sk": f"CALLBACK#{callbackId}",
            "callbackId": callbackId,
            "recordType": "callback",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "eventPath": path,
            "headers": self.safeHeaders(headers),
            "body": storedPayload,
            "bodyS3Key": s3Key if storedPayload is None else "",
            "receivedAt": now,
            **{key: value for key, value in correlationIds.items() if value and key not in {"hipId", "hiuId", "hasKeyMaterial"}},
        }
        self.dbService.putItem(TableName.REQUEST_LOG.value, item)
        return item

    def storeWebhookEvent(self, event: dict[str, Any]) -> None:
        item = {
            "pk": f"HOSP#{event['hospitalId']}",
            "sk": f"WEBHOOK#{event['eventId']}",
            "recordType": "webhookEvent",
            "status": "queued",
            "createdAt": DateTimeUtils.utcnowIso(),
            **event,
        }
        self.dbService.putItem(TableName.WEBHOOK_EVENTS.value, item)

    @staticmethod
    def safeHeaders(headers: dict[str, Any]) -> dict[str, str]:
        redacted = {"authorization", "x-api-key", "cookie", "set-cookie"}
        safe: dict[str, str] = {}
        for key, value in headers.items():
            textKey = str(key)
            safe[textKey] = "[REDACTED]" if textKey.lower() in redacted else str(value)
        return safe
