from __future__ import annotations

from typing import Any

from common.abdm.callbackCorrelationService import CallbackCorrelationService
from common.constants.indexNames import IndexName
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from modules.abdmCallbackConsumer.abdmCorrelationDbService import AbdmCorrelationDbService


class AbdmCallbackCorrelationService:
    def __init__(self, dbService: AbdmCorrelationDbService | None = None, tenantDbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or AbdmCorrelationDbService()
        self.tenantDb = tenantDbService or DynamoDbService()
        self.extractor = CallbackCorrelationService()

    def resolveHospitalId(self, abdmPath: str, payload: dict[str, Any], hospitalIdHint: str = "") -> str | None:
        if hospitalIdHint:
            return hospitalIdHint
        ids = self.extractor.extractCorrelationIds(abdmPath, {}, payload)
        hospitalId = self.dbService.findHospitalId(
            requestId=ids.get("requestId") or "",
            transactionId=ids.get("transactionId") or "",
            consentId=ids.get("consentId") or "",
            consentRequestId=ids.get("consentRequestId") or "",
        )
        if hospitalId:
            return hospitalId
        # Fallback: look up by hipId from the tenant table
        hipId = ids.get("hipId") or ""
        if hipId:
            items = self.tenantDb.queryIndex(TableName.HOSPITAL_TENANTS.value, IndexName.HIP_ID_INDEX.value, "hipId", hipId, limit=1)
            if items:
                return str(items[0].get("hospitalId") or "")
        return None
