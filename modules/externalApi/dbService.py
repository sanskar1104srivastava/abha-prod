from __future__ import annotations

from typing import Any

from common.abdm.abdmCryptoService import AbdmCryptoService
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class ExternalApiDbService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()

    def putCareContext(self, hospitalId: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = DateTimeUtils.utcnowIso()
        item = {
            "pk": f"HOSP#{hospitalId}",
            "sk": f"CARE#{payload['careContextReference']}",
            "hospitalId": hospitalId,
            "careContextReference": payload["careContextReference"],
            "recordType": "careContext",
            "createdAt": now,
            "updatedAt": now,
            **payload,
        }
        self.dbService.putItem(TableName.CARE_CONTEXTS.value, item)
        return item

    def getCareContext(self, hospitalId: str, careContextReference: str) -> dict[str, Any] | None:
        return self.dbService.getItem(
            TableName.CARE_CONTEXTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"CARE#{careContextReference}"},
        )

    def getHospitalProfile(self, hospitalId: str) -> dict[str, Any] | None:
        return self.dbService.getItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
        )

    def getInboundDataPushByTrackingId(self, hospitalId: str, trackingId: str) -> dict[str, Any] | None:
        items = self.dbService.queryByPk(TableName.HEALTH_RECORDS.value, f"HOSP#{hospitalId}", skBeginsWith="DATA#", limit=500)
        for item in items:
            if item.get("trackingId") == trackingId:
                return item
        return None

    def getDecryptedRecordsByTrackingId(self, hospitalId: str, trackingId: str) -> list[dict[str, Any]]:
        items = self.dbService.queryByPk(
            TableName.HEALTH_RECORDS.value, f"HOSP#{hospitalId}", skBeginsWith=f"RECORD#{trackingId}#", limit=500
        )
        if not items:
            # Records stored before the trackingId-prefixed sk layout
            legacy = self.dbService.queryByPk(TableName.HEALTH_RECORDS.value, f"HOSP#{hospitalId}", skBeginsWith="RECORD#", limit=500)
            items = [item for item in legacy if item.get("trackingId") == trackingId]
        return [item for item in items if item.get("decryptedS3Key")]

    def recordAccessAudit(self, hospitalId: str, action: str, details: dict[str, Any]) -> None:
        """Persist who accessed which health data, and when. Audit items carry no
        expiresAt on purpose — they must outlive the data they describe."""
        now = DateTimeUtils.utcnowIso()
        self.dbService.putItem(
            TableName.HEALTH_RECORDS.value,
            {
                "pk": f"HOSP#{hospitalId}",
                "sk": f"AUDIT#{now}#{AbdmCryptoService.newEventId()}",
                "recordType": "accessAudit",
                "hospitalId": hospitalId,
                "action": action,
                "createdAt": now,
                **details,
            },
        )
