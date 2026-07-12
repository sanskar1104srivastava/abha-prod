from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr

from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.utils.dateTimeUtils import DateTimeUtils


class AuthDbService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.db = dbService or DynamoDbService()

    # ── Hospital profile ─────────────────────────────────────────────────────

    def getProfile(self, hospitalId: str) -> dict[str, Any] | None:
        return self.db.getItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
            consistentRead=True,
        )

    def getLoginRef(self, loginId: str) -> dict[str, Any] | None:
        return self.db.getItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"LOGIN#{loginId.lower()}", "sk": "REF"},
            consistentRead=True,
        )

    def createHospital(
        self,
        hospitalId: str,
        loginId: str,
        passwordHash: str,
        hospitalName: str,
        hipId: str,
        hiuId: str,
        webhookUrl: str | None,
        webhookSecret: str | None,
        activeKeyHash: str,
        environment: str,
        dataPushUrl: str | None = None,
    ) -> None:
        now = DateTimeUtils.utcnowIso()
        # Main profile record
        self.db.putItem(
            TableName.HOSPITAL_TENANTS.value,
            {
                "pk": f"HOSP#{hospitalId}",
                "sk": "PROFILE",
                "hospitalId": hospitalId,
                "loginId": loginId.lower(),
                "passwordHash": passwordHash,
                "hospitalName": hospitalName,
                "hipId": hipId,
                "hiuId": hiuId,
                "webhookUrl": webhookUrl or "",
                "webhookSecret": webhookSecret or "",
                "dataPushUrl": dataPushUrl or "",
                "status": "active",
                "environment": environment,
                "activeKeyHash": activeKeyHash,
                "createdAt": now,
                "updatedAt": now,
            },
        )
        # Login index record — enables lookup by loginId without a GSI
        self.db.putItem(
            TableName.HOSPITAL_TENANTS.value,
            {
                "pk": f"LOGIN#{loginId.lower()}",
                "sk": "REF",
                "hospitalId": hospitalId,
                "createdAt": now,
            },
        )

    def updateActiveKeyHash(self, hospitalId: str, newKeyHash: str) -> None:
        self.db.updateItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
            "SET activeKeyHash = :h, updatedAt = :ts",
            {":h": newKeyHash, ":ts": DateTimeUtils.utcnowIso()},
        )

    def updateWebhook(self, hospitalId: str, webhookUrl: str, webhookSecret: str) -> None:
        self.db.updateItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
            "SET webhookUrl = :u, webhookSecret = :s, updatedAt = :ts",
            {":u": webhookUrl, ":s": webhookSecret, ":ts": DateTimeUtils.utcnowIso()},
        )

    def updateDataPushUrl(self, hospitalId: str, dataPushUrl: str) -> None:
        self.db.updateItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
            "SET dataPushUrl = :u, updatedAt = :ts",
            {":u": dataPushUrl, ":ts": DateTimeUtils.utcnowIso()},
        )

    # ── API keys ─────────────────────────────────────────────────────────────

    def putApiKey(
        self,
        apiKeyHash: str,
        hospitalId: str,
        hipId: str,
        hiuId: str,
        environment: str,
    ) -> None:
        self.db.putItem(
            TableName.API_KEYS.value,
            {
                "apiKeyHash": apiKeyHash,
                "hospitalId": hospitalId,
                "hipId": hipId,
                "hiuId": hiuId,
                "status": "active",
                "environment": environment,
                "createdAt": DateTimeUtils.utcnowIso(),
            },
        )

    def deactivateApiKey(self, apiKeyHash: str) -> None:
        if not apiKeyHash:
            return
        self.db.updateItem(
            TableName.API_KEYS.value,
            {"apiKeyHash": apiKeyHash},
            "SET #s = :inactive, updatedAt = :ts",
            {":inactive": "inactive", ":ts": DateTimeUtils.utcnowIso()},
            {"#s": "status"},
        )
