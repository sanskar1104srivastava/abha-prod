from __future__ import annotations

from typing import Any

from common.abdm.abdmCryptoService import AbdmCryptoService
from common.config.settings import getSettings
from common.constants.eventTypes import EventType
from common.constants.indexNames import IndexName
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class RequestLogService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()
        self.settings = getSettings()

    def createAcceptedRequest(
        self,
        hospitalId: str,
        flowType: str,
        requestPayload: dict[str, Any],
        correlation: dict[str, str] | None = None,
    ) -> dict[str, str]:
        now = DateTimeUtils.utcnowIso()
        trackingId = AbdmCryptoService.newTrackingId()
        requestId = (correlation or {}).get("requestId") or AbdmCryptoService.newRequestId()
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"REQ#{trackingId}",
            "recordType": "request",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "flowType": flowType,
            "requestId": requestId,
            "status": "accepted",
            "requestPayload": requestPayload,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
            **(correlation or {}),
        }
        self.dbService.putItem(TableName.REQUEST_LOG.value, item)
        self.updateStatus(hospitalId, trackingId, "accepted", EventType.CALLBACK_RECEIVED.value, {"flowType": flowType})
        return {"trackingId": trackingId, "requestId": requestId}

    def updateStatus(
        self,
        hospitalId: str,
        trackingId: str,
        status: str,
        eventType: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = DateTimeUtils.utcnowIso()
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"STATUS#{trackingId}",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "status": status,
            "eventType": eventType,
            "details": details or {},
            "updatedAt": now,
        }
        self.dbService.putItem(TableName.STATUS_STORE.value, item)
        return item

    def getStatus(self, hospitalId: str, trackingId: str) -> dict[str, Any] | None:
        return self.dbService.getItem(TableName.STATUS_STORE.value, {"pk": f"HOSP#{hospitalId}", "sk": f"STATUS#{trackingId}"})

    def findByCorrelationIds(self, correlationIds: dict[str, str]) -> dict[str, Any] | None:
        lookups = [
            ("requestId", IndexName.REQUEST_ID_INDEX.value, correlationIds.get("requestId", "")),
            ("transactionId", IndexName.TRANSACTION_ID_INDEX.value, correlationIds.get("transactionId", "")),
            ("consentRequestId", IndexName.CONSENT_REQUEST_ID_INDEX.value, correlationIds.get("consentRequestId", "")),
            ("consentId", IndexName.CONSENT_ID_INDEX.value, correlationIds.get("consentId", "")),
        ]
        for keyName, indexName, keyValue in lookups:
            if not keyValue:
                continue
            rows = self.dbService.queryIndex(TableName.REQUEST_LOG.value, indexName, keyName, keyValue, limit=20)
            matched = self.resolveCanonicalRequest(rows)
            if matched:
                return matched
        return None

    def resolveCanonicalRequest(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        for row in rows:
            if str(row.get("recordType") or "") == "request" and str(row.get("trackingId") or "").strip():
                return row
        for row in rows:
            requestRow = self.getRequestRowForTracking(row)
            if requestRow:
                return requestRow
        for row in rows:
            if str(row.get("trackingId") or "").strip():
                return row
        return None

    def getRequestRowForTracking(self, row: dict[str, Any]) -> dict[str, Any] | None:
        hospitalId = str(row.get("hospitalId") or "").strip()
        trackingId = str(row.get("trackingId") or "").strip()
        if not hospitalId or not trackingId:
            return None
        return self.dbService.getItem(
            TableName.REQUEST_LOG.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"REQ#{trackingId}"},
            consistentRead=True,
        )

    def recordCallback(self, hospitalId: str, trackingId: str, callbackId: str, callbackItem: dict[str, Any]) -> None:
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"CALLBACK#{callbackId}",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            **callbackItem,
        }
        self.dbService.putItem(TableName.REQUEST_LOG.value, item)

    def recordConsentArtefactIndex(self, hospitalId: str, trackingId: str, consentRequestId: str, consentId: str) -> None:
        if not hospitalId or not trackingId or not consentId:
            return
        now = DateTimeUtils.utcnowIso()
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"ARTEFACT#{trackingId}#{consentId}",
            "recordType": "consentArtefact",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "consentId": consentId,
            "consentRequestId": consentRequestId,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
        }
        self.dbService.putItem(TableName.REQUEST_LOG.value, item)

    def recordConsentFetchRequest(
        self,
        hospitalId: str,
        trackingId: str,
        requestId: str,
        consentRequestId: str,
        consentId: str,
        requestPayload: dict[str, Any],
    ) -> None:
        if not hospitalId or not trackingId or not requestId or not consentId:
            return
        now = DateTimeUtils.utcnowIso()
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"FETCH#{trackingId}#{consentId}",
            "recordType": "consentFetch",
            "flowType": "external.consent.fetch",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "requestId": requestId,
            "consentId": consentId,
            "consentRequestId": consentRequestId,
            "status": "accepted",
            "requestPayload": requestPayload,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
        }
        self.dbService.putItem(TableName.REQUEST_LOG.value, item)

    def findConsentFetchByRequestId(self, requestId: str) -> dict[str, Any] | None:
        requestId = str(requestId or "").strip()
        if not requestId:
            return None
        rows = self.dbService.queryIndex(
            TableName.REQUEST_LOG.value,
            IndexName.REQUEST_ID_INDEX.value,
            "requestId",
            requestId,
            limit=20,
        )
        for row in rows:
            if str(row.get("recordType") or "") == "consentFetch":
                return row
        return None

    def backfillCorrelation(self, hospitalId: str, trackingId: str, newCorrelationIds: dict[str, str]) -> None:
        updateable = {"consentRequestId", "transactionId", "consentId"}
        updates = {k: v for k, v in newCorrelationIds.items() if k in updateable and v}
        if not updates:
            return
        expressions = []
        for key in updates:
            if key == "transactionId":
                expressions.append("transactionId = :transactionId")
                expressions.append("abdmTransactionId = :transactionId")
            elif key == "consentRequestId":
                expressions.append("consentRequestId = :consentRequestId")
            else:
                expressions.append(f"{key} = if_not_exists({key}, :{key})")
        self.dbService.updateItem(
            TableName.REQUEST_LOG.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"REQ#{trackingId}"},
            "SET " + ", ".join(expressions),
            {f":{k}": v for k, v in updates.items()},
        )
