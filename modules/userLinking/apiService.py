from __future__ import annotations

from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from modules.userLinking.requests import OnConfirmRequest, OnDiscoverRequest, OnInitRequest


class UserLinkingApiService:
    def __init__(self, abdmClient: AbdmClient | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.logger = LoggingService("userLinking.apiService")

    async def respondDiscovery(self, requestBody: OnDiscoverRequest) -> dict[str, Any]:
        """HIP responds to ABDM patient discovery. Call after receiving the discovery webhook."""
        self.logger.logInput("respondDiscovery", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "transactionId": requestBody.transactionId,
            "patient": requestBody.patient,
            "resp": requestBody.resp,
        }
        return await self.abdmClient.hipPost("userLinkOnDiscover", payload)

    async def respondLinkInit(self, requestBody: OnInitRequest) -> dict[str, Any]:
        """HIP responds to ABDM link-init. Call after OTP is sent to the patient."""
        self.logger.logInput("respondLinkInit", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "transactionId": requestBody.transactionId,
            "link": requestBody.link,
            "resp": requestBody.resp,
        }
        return await self.abdmClient.hipPost("userLinkOnInit", payload)

    async def respondLinkConfirm(self, requestBody: OnConfirmRequest) -> dict[str, Any]:
        """HIP confirms link after OTP verified by the patient."""
        self.logger.logInput("respondLinkConfirm", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "transactionId": requestBody.transactionId,
            "patient": requestBody.patient,
            "resp": requestBody.resp,
        }
        return await self.abdmClient.hipPost("userLinkOnConfirm", payload)
