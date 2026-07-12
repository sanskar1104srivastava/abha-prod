from __future__ import annotations

from typing import Any

import httpx

from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.logging.loggingService import LoggingService
from common.security.webhookSignatureService import WebhookSignatureService


class AbdmCallbackForwarderService:
    def __init__(self, dbService: DynamoDbService | None = None) -> None:
        self.dbService = dbService or DynamoDbService()
        self.signer = WebhookSignatureService()
        self.logger = LoggingService("abdmCallbackForwarder")

    def _getTenant(self, hospitalId: str) -> dict[str, Any] | None:
        return self.dbService.getItem(
            TableName.HOSPITAL_TENANTS.value,
            {"pk": f"HOSP#{hospitalId}", "sk": "PROFILE"},
        )

    async def forward(self, hospitalId: str, abdmPath: str, rawBody: str) -> tuple[bool, bool]:
        """POST raw ABDM body to the hospital webhook. Returns (success, retryable)."""
        tenant = self._getTenant(hospitalId)
        if not tenant:
            self.logger.logProcess("noTenantConfig", hospitalId=hospitalId)
            return False, False

        webhookUrl = str(tenant.get("webhookUrl") or "").strip()
        webhookSecret = str(tenant.get("webhookSecret") or "").strip()
        if not webhookUrl or not webhookSecret:
            self.logger.logProcess("tenantConfigIncomplete", hospitalId=hospitalId)
            return False, False

        signature = self.signer.signPayload(webhookSecret, rawBody)
        headers = {
            "Content-Type": "application/json",
            "X-Abdm-Path": abdmPath,
            "X-Abdm-Signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(webhookUrl, content=rawBody.encode(), headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            self.logger.logError("forwardNetworkError", exc, hospitalId=hospitalId, path=abdmPath)
            return False, True

        if response.status_code >= 500:
            self.logger.logProcess("forwardServerError", hospitalId=hospitalId, statusCode=str(response.status_code), path=abdmPath)
            return False, True

        if response.status_code >= 400:
            self.logger.logProcess("forwardClientError", hospitalId=hospitalId, statusCode=str(response.status_code), path=abdmPath)
            return False, False

        self.logger.logProcess("forwarded", hospitalId=hospitalId, statusCode=str(response.status_code), path=abdmPath)
        return True, False
