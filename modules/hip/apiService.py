from __future__ import annotations

from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.config.settings import getSettings
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from modules.hip.requests import (
    CareContextNotifyRequest,
    ConsentOnNotifyRequest,
    FetchModesRequest,
    HealthInfoOnRequestRequest,
    OtpConfirmRequest,
    OtpInitRequest,
    SmsNotifyRequest,
)


class HipApiService:
    def __init__(self, abdmClient: AbdmClient | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.settings = getSettings()
        self.logger = LoggingService("hip.apiService")

    async def fetchModes(self, requestBody: FetchModesRequest) -> dict[str, Any]:
        """Fetch available patient auth modes for HIP-initiated linking."""
        self.logger.logInput("fetchModes", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "query": {
                "patient": {"id": requestBody.abhaAddress},
                "purpose": requestBody.purpose,
                "requester": {"type": "HIP", "id": self.settings.abdmHipId},
            },
        }
        return await self.abdmClient.hipPost("hipFetchModes", payload)

    async def otpInit(self, requestBody: OtpInitRequest) -> dict[str, Any]:
        """Initiate OTP auth for HIP-initiated linking."""
        self.logger.logInput("otpInit", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "query": {
                "id": requestBody.abhaAddress,
                "purpose": requestBody.purpose,
                "authMode": requestBody.authMode,
                "requester": {"type": "HIP", "id": self.settings.abdmHipId},
            },
        }
        return await self.abdmClient.hipPost("hipOtpInit", payload)

    async def otpConfirm(self, requestBody: OtpConfirmRequest) -> dict[str, Any]:
        """Confirm OTP auth; on success ABDM delivers a link token via the callback URL."""
        self.logger.logInput("otpConfirm", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "transactionId": requestBody.transactionId,
            "credential": {"authCode": requestBody.otp},
        }
        return await self.abdmClient.hipPost("hipOtpConfirm", payload)

    async def notifyCareContext(self, requestBody: CareContextNotifyRequest) -> dict[str, Any]:
        """Notify ABDM gateway that a care context has been linked."""
        self.logger.logInput("notifyCareContext", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "notification": {
                "patient": {"id": requestBody.abhaAddress},
                "careContext": {
                    "patientReference": requestBody.patientReference,
                    "careContextReference": requestBody.careContextReference,
                },
                "hiTypes": requestBody.hiTypes,
                "date": DateTimeUtils.utcnowIso(),
                "hip": {"id": self.settings.abdmHipId},
            },
        }
        extraHeaders = {"X-link-token": f"Bearer {requestBody.linkToken}"}
        return await self.abdmClient.hipPost("hipContextNotify", payload, extraHeaders)

    async def consentOnNotify(self, requestBody: ConsentOnNotifyRequest) -> dict[str, Any]:
        """Send HIP acknowledgement to ABDM for a consent notification."""
        self.logger.logInput("consentOnNotify", body=requestBody.model_dump(mode="json"))
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "acknowledgement": {
                "status": requestBody.status,
                "consentId": requestBody.consentId,
            },
            "response": {"requestId": requestBody.requestId},
        }
        return await self.abdmClient.hipPost("consentHipOnNotify", payload)

    async def smsNotify(self, requestBody: SmsNotifyRequest) -> dict[str, Any]:
        """Send deep-link SMS to a patient so they can link care contexts via the ABDM app."""
        self.logger.logInput("smsNotify", body={"phoneNo": requestBody.phoneNo})
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
                "hip": {"name": self.settings.abdmHipId, "id": self.settings.abdmHipId},
            },
        }
        return await self.abdmClient.postGateway(self.settings.abdmEndpoint("hipSmsNotify"), payload, headers)

    async def healthInfoOnRequest(self, requestBody: HealthInfoOnRequestRequest) -> dict[str, Any]:
        """Send HIP acknowledgement to ABDM for a health-information request."""
        self.logger.logInput("healthInfoOnRequest", body=requestBody.model_dump(mode="json"))
        hiRequest: dict[str, Any] = {
            "transactionId": requestBody.transactionId,
            "sessionStatus": requestBody.sessionStatus,
        }
        if requestBody.careContextReferences:
            hiRequest["careContextsStatus"] = [
                {"careContextReference": ref, "hiStatus": "OK"}
                for ref in requestBody.careContextReferences
            ]
        payload: dict[str, Any] = {
            "requestId": AbdmCryptoService.newRequestId(),
            "timestamp": DateTimeUtils.utcnowIso(),
            "hiRequest": hiRequest,
            "response": {"requestId": requestBody.requestId},
        }
        return await self.abdmClient.hipPost("healthInformationHipOnRequest", payload)
