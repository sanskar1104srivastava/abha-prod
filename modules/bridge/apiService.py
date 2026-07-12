from __future__ import annotations

from typing import Any

import httpx

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from modules.bridge.requests import RegisterBridgeServicesRequest, SmsNotifyRequest, UpdateCallbackUrlRequest

class BridgeApiService:
    def __init__(self, abdmClient: AbdmClient | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.settings = getSettings()
        self.logger = LoggingService("bridge.apiService")

    async def updateCallbackUrl(self, requestBody: UpdateCallbackUrlRequest) -> dict[str, Any]:
        """Update the HIP/HIU callback URL with the ABDM gateway."""
        self.logger.logInput("updateCallbackUrl", body={"callbackUrl": str(requestBody.callbackUrl)})
        token = await self.abdmClient._resolveToken()
        headers: dict[str, str] = {
            **self.abdmClient._buildBaseHeaders(),
            "Authorization": f"Bearer {token}",
            "X-CM-ID": self.settings.abdmCmId,
        }
        return await self.abdmClient.patchGateway(
            self.settings.abdmEndpoint("bridgeUrl"),
            {"url": str(requestBody.callbackUrl)},
            headers,
        )

    async def registerBridgeServices(self, requestBody: RegisterBridgeServicesRequest) -> dict[str, Any]:
        """Register or update HIP/HIU bridge services with ABDM facility registry."""
        self.logger.logInput("registerBridgeServices", body=requestBody.model_dump(mode="json"))
        token = await self.abdmClient._resolveToken()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        facilityBridgeUrl = self.settings.facilityBridgeUrl
        if not facilityBridgeUrl:
            raise AppError(503, ErrorCode.INTERNAL_ERROR, "facilityBridgeUrl not configured in Secrets Manager")
        response = await self.abdmClient.client.post(
            facilityBridgeUrl,
            json={"facilityId": requestBody.facilityId, "facilityName": requestBody.facilityName, "HRP": requestBody.hrp},
            headers=headers,
        )
        if response.status_code >= 400:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM bridge registration failed", {"statusCode": response.status_code, "body": response.text[:1000]})
        return response.json() if response.text else {"status": "ok"}

    async def getBridgeServices(self) -> dict[str, Any]:
        """List all HIP/HIU services registered under this bridge with the ABDM gateway."""
        self.logger.logInput("getBridgeServices", body={})
        return await self.abdmClient.hipGet("bridgeServices")

    async def sendSmsNotify(self, requestBody: SmsNotifyRequest) -> dict[str, Any]:
        """Send deep-link SMS to a patient so they can link care contexts via ABDM app."""
        self.logger.logInput("sendSmsNotify", body=requestBody.model_dump(mode="json"))
        token = await self.abdmClient._resolveToken()
        headers: dict[str, str] = {
            **self.abdmClient._buildBaseHeaders(),
            "Authorization": f"Bearer {token}",
            "X-CM-ID": self.settings.abdmCmId,
            "X-HIP-ID": self.settings.abdmHipId,
        }
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "notification": {
                "phoneNo": requestBody.phoneNo,
                "hip": {
                    "name": self.settings.abdmHipId,
                    "id": self.settings.abdmHipId,
                },
            },
        }
        return await self.abdmClient.postGateway(
            self.settings.abdmEndpoint("hipSmsNotify"),
            payload,
            headers,
        )
