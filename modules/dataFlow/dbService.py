from __future__ import annotations

from typing import Any

from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class DataFlowDbService:
    def __init__(self, dbService: DynamoDbService | None = None, awsService: AwsService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()
        self.awsService = awsService or AwsService()
        self.settings = getSettings()

    def storeInboundDataPush(
        self,
        dataFlowId: str,
        path: str,
        headers: dict[str, Any],
        payload: dict[str, Any],
        matchedRequest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        hospitalId = str((matchedRequest or {}).get("hospitalId") or "unmatched")
        trackingId = str((matchedRequest or {}).get("trackingId") or "")
        now = DateTimeUtils.utcnowIso()
        s3Key = f"inbound-data/{DateTimeUtils.utcDatePath()}/{dataFlowId}.json"
        if self.settings.encryptedRecordsBucket:
            self.awsService.putJsonObject(
                self.settings.encryptedRecordsBucket,
                s3Key,
                {"path": path, "headers": self.safeHeaders(headers), "payload": payload, "receivedAt": now},
            )
        item = {
            "pk": f"HOSP#{hospitalId}" if hospitalId != "unmatched" else "UNMATCHED",
            "sk": f"DATA#{dataFlowId}",
            "recordType": "inboundDataPush",
            "dataFlowId": dataFlowId,
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "transactionId": str(payload.get("transactionId") or ""),
            "consentId": str(payload.get("consentId") or ""),
            "encryptedS3Key": s3Key,
            "entryCount": len(payload.get("entries") or []),
            "status": "encryptedStored",
            "receivedAt": now,
            "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
        }
        self.dbService.putItem(TableName.HEALTH_RECORDS.value, item)
        return item

    def storeDecryptedRecord(
        self,
        hospitalId: str,
        trackingId: str,
        dataFlowId: str,
        recordId: str,
        entry: dict[str, Any],
        decryptedPayload: dict[str, Any],
    ) -> None:
        s3Key = f"decrypted-data/{DateTimeUtils.utcDatePath()}/{recordId}.json"
        if self.settings.decryptedRecordsBucket:
            self.awsService.putJsonObject(self.settings.decryptedRecordsBucket, s3Key, decryptedPayload)
        # sk is prefixed with trackingId so records for one request can be fetched
        # with a strict key-scoped query instead of filtering the whole partition
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"RECORD#{trackingId}#{recordId}",
            "recordType": "healthRecord",
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "dataFlowId": dataFlowId,
            "recordId": recordId,
            "transactionId": str(entry.get("transactionId") or ""),
            "careContextReference": str(entry.get("careContextReference") or ""),
            "media": str(entry.get("media") or ""),
            "status": "decrypted",
            "decryptedS3Key": s3Key,
            "createdAt": DateTimeUtils.utcnowIso(),
            "expiresAt": DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400,
        }
        self.dbService.putItem(TableName.HEALTH_RECORDS.value, item)

    def getCareContext(self, hospitalId: str, careContextReference: str) -> dict[str, Any] | None:
        return self.dbService.getItem(
            TableName.CARE_CONTEXTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"CARE#{careContextReference}"},
        )

    def hydrateTemporaryCareContextDocument(self, careContext: dict[str, Any]) -> dict[str, Any]:
        if careContext.get("documentData") or not careContext.get("temporaryDocumentS3Key"):
            return careContext
        bucket = str(careContext.get("temporaryDocumentBucket") or self.settings.encryptedRecordsBucket or "")
        s3Key = str(careContext.get("temporaryDocumentS3Key") or "")
        if not bucket or not s3Key:
            return careContext
        storedDocument = self.awsService.getJsonObject(bucket, s3Key)
        hydrated = dict(careContext)
        hydrated["documentData"] = storedDocument.get("documentData") or ""
        if not hydrated.get("documentTitle"):
            hydrated["documentTitle"] = storedDocument.get("documentTitle") or None
        if not hydrated.get("documentContentType"):
            hydrated["documentContentType"] = storedDocument.get("documentContentType") or None
        return hydrated

    def deleteTemporaryCareContext(self, hospitalId: str, careContextReference: str, careContext: dict[str, Any]) -> str:
        if not careContext.get("temporaryCareContext"):
            return "skipped:not-temporary"
        bucket = str(careContext.get("temporaryDocumentBucket") or self.settings.encryptedRecordsBucket or "")
        s3Key = str(careContext.get("temporaryDocumentS3Key") or "")
        if bucket and s3Key:
            self.awsService.deleteObject(bucket, s3Key)
        self.dbService.deleteItem(
            TableName.CARE_CONTEXTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"CARE#{careContextReference}"},
        )
        return "deleted"

    def storeJobResult(self, hospitalId: str, trackingId: str, jobId: str, result: dict[str, Any]) -> None:
        self.dbService.putItem(
            TableName.STATUS_STORE.value,
            {
                "pk": f"HOSP#{hospitalId}",
                "sk": f"DATAFLOW#{jobId}",
                "recordType": "dataFlowJobResult",
                "hospitalId": hospitalId,
                "trackingId": trackingId,
                "jobId": jobId,
                "updatedAt": DateTimeUtils.utcnowIso(),
                **result,
            },
        )

    @staticmethod
    def safeHeaders(headers: dict[str, Any]) -> dict[str, str]:
        redacted = {"authorization", "x-api-key", "cookie", "set-cookie"}
        return {str(key): ("[REDACTED]" if str(key).lower() in redacted else str(value)) for key, value in headers.items()}
