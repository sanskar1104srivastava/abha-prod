from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.logging.loggingService import LoggingService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.hip.apiService import HipApiService
from modules.hip.requests import (
    CareContextNotifyRequest,
    ConsentOnNotifyRequest,
    FetchModesRequest,
    HealthInfoOnRequestRequest,
    OtpConfirmRequest,
    OtpInitRequest,
    SmsNotifyRequest,
)

router = APIRouter()
apiService = HipApiService()
authService = ApiKeyAuthService()
logger = LoggingService("hip.routes")


def _authenticate(request: Request) -> None:
    authService.authenticate(dict(request.headers))


@router.post("/v1/hip/link/fetch-modes")
async def fetchModes(request: Request, requestBody: FetchModesRequest) -> dict[str, Any]:
    """
    Fetch available auth modes for a patient at this HIP.

    Call this before otp-init to know which modes (MOBILE_OTP, AADHAAR_OTP, etc.)
    the patient can use. ABDM responds via the callback URL.
    """
    _authenticate(request)
    logger.logInput("fetchModes", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.fetchModes(requestBody)


@router.post("/v1/hip/link/otp-init")
async def otpInit(request: Request, requestBody: OtpInitRequest) -> dict[str, Any]:
    """
    Initiate OTP-based auth for HIP-initiated care context linking.

    ABDM sends an OTP to the patient's mobile or Aadhaar-linked mobile.
    The transactionId is returned via callback.
    """
    _authenticate(request)
    logger.logInput("otpInit", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.otpInit(requestBody)


@router.post("/v1/hip/link/otp-confirm")
async def otpConfirm(request: Request, requestBody: OtpConfirmRequest) -> dict[str, Any]:
    """
    Confirm OTP entered by the patient.

    On success, ABDM delivers a linkToken to the registered callback URL.
    Use that linkToken when calling POST /v1/care-contexts/link.
    """
    _authenticate(request)
    logger.logInput("otpConfirm", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.otpConfirm(requestBody)


@router.post("/v1/hip/link/care-context/notify")
async def notifyCareContext(request: Request, requestBody: CareContextNotifyRequest) -> dict[str, Any]:
    """
    Notify ABDM that a care context has been linked to a patient's ABHA.

    Call after successfully linking via POST /v1/care-contexts/link.
    Requires the linkToken from the linking flow.
    """
    _authenticate(request)
    logger.logInput("notifyCareContext", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.notifyCareContext(requestBody)


@router.post("/v1/hip/sms-notify")
async def smsNotify(request: Request, requestBody: SmsNotifyRequest) -> dict[str, Any]:
    """
    Send a deep-link SMS to a patient so they can link care contexts via the ABDM app.

    Use when a patient is at the hospital but does not have the ABDM app open.
    ABDM sends an SMS that opens the app on the care-context linking screen for this HIP.
    phoneNo must include the country code prefix: +919876543210
    """
    _authenticate(request)
    logger.logInput("smsNotify", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.smsNotify(requestBody)


@router.post("/v1/hip/consent/on-notify")
async def consentOnNotify(request: Request, requestBody: ConsentOnNotifyRequest) -> dict[str, Any]:
    """
    Send HIP acknowledgement to ABDM for a consent notification.

    Call this after receiving a consent notification webhook to let ABDM
    know the HIP has processed it.
    """
    _authenticate(request)
    logger.logInput("consentOnNotify", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.consentOnNotify(requestBody)


@router.post("/v1/hip/health-information/on-request")
async def healthInfoOnRequest(request: Request, requestBody: HealthInfoOnRequestRequest) -> dict[str, Any]:
    """
    Send HIP acknowledgement to ABDM for a health-information request.

    The data-flow Lambda handles this automatically when processing the
    SQS job. Call this manually only if you need explicit acknowledgement
    control before data is pushed.
    """
    _authenticate(request)
    logger.logInput("healthInfoOnRequest", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.healthInfoOnRequest(requestBody)
