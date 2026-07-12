from __future__ import annotations

import time
from typing import Any

from common.db.dynamoDbService import DynamoDbService

_TABLE = "abdmCorrelation"
_TTL_SECONDS = 30 * 24 * 3600

_PREFIXES: dict[str, str] = {
    "requestId": "req#",
    "transactionId": "txn#",
    "consentId": "cid#",
    "consentRequestId": "crid#",
}


class AbdmCorrelationDbService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()

    def storeCorrelationIds(self, hospitalId: str, correlationIds: dict[str, str]) -> None:
        ttl = int(time.time()) + _TTL_SECONDS
        for key, value in correlationIds.items():
            prefix = _PREFIXES.get(key)
            if not prefix or not str(value or "").strip():
                continue
            self.dbService.putItem(
                _TABLE,
                {"pk": f"{prefix}{value}", "hospitalId": hospitalId, "ttl": ttl},
            )

    def findHospitalId(
        self,
        requestId: str = "",
        transactionId: str = "",
        consentId: str = "",
        consentRequestId: str = "",
    ) -> str | None:
        candidates = [
            f"req#{requestId}" if requestId else "",
            f"txn#{transactionId}" if transactionId else "",
            f"cid#{consentId}" if consentId else "",
            f"crid#{consentRequestId}" if consentRequestId else "",
        ]
        for pk in filter(None, candidates):
            item = self.dbService.getItem(_TABLE, {"pk": pk})
            if item:
                return str(item.get("hospitalId") or "")
        return None
