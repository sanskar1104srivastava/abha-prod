from __future__ import annotations

from typing import Any

from common.config.settings import getSettings
from common.logging.loggingService import LoggingService
from modules.admin.requests import CreateCustomerRequest
from modules.auth.apiService import AuthService
from modules.auth.requests import HospitalRegisterRequest
from modules.bridge.apiService import BridgeApiService
from modules.bridge.requests import RegisterBridgeServicesRequest, UpdateCallbackUrlRequest


class AdminApiService:
    def __init__(
        self,
        authService: AuthService | None = None,
        bridgeService: BridgeApiService | None = None,
    ) -> None:
        self.authService = authService or AuthService()
        self.bridgeService = bridgeService or BridgeApiService()
        self.settings = getSettings()
        self.logger = LoggingService("admin.apiService")

    async def createCustomer(self, request: CreateCustomerRequest) -> dict[str, Any]:
        registerReq = HospitalRegisterRequest(
            loginId=request.loginId,
            password=request.password,
            hospitalName=request.hospitalName,
            hipId=request.hipId,
            hiuId=request.hiuId,
            webhookUrl=request.webhookUrl,
            webhookSecret=request.webhookSecret,
            dataPushUrl=request.dataPushUrl,
        )
        result = self.authService.register(registerReq)
        self.logger.logProcess("customerCreated", hospitalId=result.get("hospitalId"), loginId=request.loginId)

        bridgeResult: dict[str, Any] = {}
        if request.setupBridge:
            bridgeResult = await self._autoSetupBridge(request)

        return {**result, "bridgeSetup": bridgeResult}

    async def _autoSetupBridge(self, request: CreateCustomerRequest) -> dict[str, Any]:
        callbackUrl = self.settings.selfCallbackUrl
        if not callbackUrl:
            self.logger.logProcess("bridgeSetupSkipped", reason="selfCallbackUrl not configured in Secrets Manager")
            return {"status": "skipped", "reason": "selfCallbackUrl not configured"}

        facilityId   = request.facilityId   or request.hipId
        facilityName = request.facilityName or request.hospitalName

        hrp = request.hrp or [
            {
                "id": facilityId,
                "name": facilityName,
                "type": "HIP",
                "isActive": True,
                "endpoints": [
                    {"use": "KYC_AND_LINKING", "type": "FHIR", "bridge": callbackUrl}
                ],
            }
        ]

        try:
            callbackResult = await self.bridgeService.updateCallbackUrl(
                UpdateCallbackUrlRequest(callbackUrl=callbackUrl)  # type: ignore[arg-type]
            )
        except Exception as exc:
            self.logger.logError("bridgeCallbackUrlFailed", exc)
            return {"status": "failed", "step": "updateCallbackUrl", "error": str(exc)}

        try:
            servicesResult = await self.bridgeService.registerBridgeServices(
                RegisterBridgeServicesRequest(
                    facilityId=facilityId,
                    facilityName=facilityName,
                    hrp=hrp,
                )
            )
        except Exception as exc:
            self.logger.logError("bridgeServicesRegistrationFailed", exc)
            return {
                "status": "partial",
                "callbackUrl": callbackResult,
                "registerServices": {"error": str(exc)},
            }

        return {"status": "ok", "callbackUrl": callbackResult, "registerServices": servicesResult}
