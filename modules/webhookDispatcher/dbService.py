from __future__ import annotations

from typing import Any

from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class WebhookDispatcherDbService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()

    def getHospitalTenant(self, hospitalId: str) -> dict[str, Any] | None:
        return self.dbService.getItem(TableName.HOSPITAL_TENANTS.value, {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"})

    def markDelivery(self, hospitalId: str, eventId: str, result: dict[str, Any]) -> None:
        self.dbService.updateItem(
            TableName.WEBHOOK_EVENTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": f"WEBHOOK#{eventId}"},
            "SET #status = :status, deliveryResult = :result, deliveredAt = :deliveredAt",
            {
                ":status": result.get("status") or "unknown",
                ":result": result,
                ":deliveredAt": DateTimeUtils.utcnowIso(),
            },
            {"#status": "status"},
        )
