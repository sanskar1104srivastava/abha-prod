from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from common.logging.loggingService import LoggingService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.abha.apiService import AbhaApiService
from modules.abha.requests import (
    AadhaarOtpRequest,
    AadhaarVerifyOtpRequest,
    AbhaAddressSetRequest,
    AbhaMobileSearchRequest,
    AbhaNumberSearchRequest,
    AbhaProfileRequest,
    AbhaSuggestionsRequest,
    MobileOtpRequest,
    MobileVerifyOtpRequest,
    PhrOtpRequest,
    PhrSearchRequest,
    PhrVerifyOtpRequest,
)

router = APIRouter()
apiService = AbhaApiService()
authService = ApiKeyAuthService()
logger = LoggingService("abha.routes")


def _authenticate(request: Request) -> None:
    authService.authenticate(dict(request.headers))


@router.post("/v1/abha/enroll/aadhaar/request-otp")
async def enrollAadhaarRequestOtp(request: Request, requestBody: AadhaarOtpRequest) -> dict[str, Any]:
    """Step 1 of Aadhaar enrollment — sends OTP to the patient's Aadhaar-linked mobile."""
    _authenticate(request)
    logger.logInput("enrollAadhaarRequestOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.enrollAadhaarRequestOtp(requestBody)


@router.post("/v1/abha/enroll/aadhaar/verify-otp")
async def enrollAadhaarVerifyOtp(request: Request, requestBody: AadhaarVerifyOtpRequest) -> dict[str, Any]:
    """Step 2 of Aadhaar enrollment — verifies OTP and creates the ABHA account."""
    _authenticate(request)
    logger.logInput("enrollAadhaarVerifyOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.enrollAadhaarVerifyOtp(requestBody)


@router.post("/v1/abha/enroll/mobile/request-otp")
async def enrollMobileRequestOtp(request: Request, requestBody: MobileOtpRequest) -> dict[str, Any]:
    """Step 1 of mobile-only enrollment — sends OTP to the patient's mobile."""
    _authenticate(request)
    logger.logInput("enrollMobileRequestOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.enrollMobileRequestOtp(requestBody)


@router.post("/v1/abha/enroll/mobile/verify-otp")
async def enrollMobileVerifyOtp(request: Request, requestBody: MobileVerifyOtpRequest) -> dict[str, Any]:
    """Step 2 of mobile-only enrollment — verifies OTP and links mobile to ABHA."""
    _authenticate(request)
    logger.logInput("enrollMobileVerifyOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.enrollMobileVerifyOtp(requestBody)


@router.post("/v1/abha/address/suggestions")
async def getAddressSuggestions(request: Request, requestBody: AbhaSuggestionsRequest) -> dict[str, Any]:
    """Returns a list of available ABHA address suggestions for the enrollment session."""
    _authenticate(request)
    logger.logInput("getAddressSuggestions", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.getAddressSuggestions(requestBody)


@router.post("/v1/abha/address/set")
async def setAbhaAddress(request: Request, requestBody: AbhaAddressSetRequest) -> dict[str, Any]:
    """Sets the patient's preferred ABHA address from the suggestions list."""
    _authenticate(request)
    logger.logInput("setAbhaAddress", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.setAbhaAddress(requestBody)


@router.post("/v1/abha/search/by-mobile")
async def searchByMobile(request: Request, requestBody: AbhaMobileSearchRequest) -> dict[str, Any]:
    """Find all ABHA accounts linked to a patient's mobile number."""
    _authenticate(request)
    logger.logInput("searchByMobile", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.searchByMobile(requestBody)


@router.post("/v1/abha/search/by-abha-number")
async def searchByAbhaNumber(request: Request, requestBody: AbhaNumberSearchRequest) -> dict[str, Any]:
    """Look up ABHA profile by 14-digit ABHA number (for linking existing ABHA to patient)."""
    _authenticate(request)
    logger.logInput("searchByAbhaNumber", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.searchByAbhaNumber(requestBody)


@router.post("/v1/abha/phr/search")
async def phrSearch(request: Request, requestBody: PhrSearchRequest) -> dict[str, Any]:
    """Check whether an ABHA address exists (returns profile info for display)."""
    _authenticate(request)
    logger.logInput("phrSearch", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.phrSearch(requestBody)


@router.post("/v1/abha/phr/send-otp")
async def phrSendOtp(request: Request, requestBody: PhrOtpRequest) -> dict[str, Any]:
    """Send OTP to the ABHA address holder for PHR-based login."""
    _authenticate(request)
    logger.logInput("phrSendOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.phrSendOtp(requestBody)


@router.post("/v1/abha/phr/verify-otp")
async def phrVerifyOtp(request: Request, requestBody: PhrVerifyOtpRequest) -> dict[str, Any]:
    """Verify PHR OTP and get phrToken (use phrToken for profile/card/QR)."""
    _authenticate(request)
    logger.logInput("phrVerifyOtp", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.phrVerifyOtp(requestBody)


@router.post("/v1/abha/profile/details")
async def getProfileDetails(request: Request, requestBody: AbhaProfileRequest) -> dict[str, Any]:
    """Fetch full ABHA profile using the xToken from a lookup/verify-otp or phr/verify-otp response."""
    _authenticate(request)
    logger.logInput("getProfileDetails", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.getProfileDetails(requestBody)


@router.post("/v1/abha/profile/card")
async def getAbhaCard(request: Request, requestBody: AbhaProfileRequest) -> Response:
    """Download the ABHA health card as a PDF (binary). Pass xToken from lookup/verify-otp."""
    _authenticate(request)
    logger.logInput("getAbhaCard", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    data = await apiService.getAbhaCard(requestBody)
    return Response(content=data, media_type="application/pdf")


@router.post("/v1/abha/profile/qr-code")
async def getAbhaQrCode(request: Request, requestBody: AbhaProfileRequest) -> Response:
    """Download the ABHA QR code image (binary PNG). Pass xToken from lookup/verify-otp."""
    _authenticate(request)
    logger.logInput("getAbhaQrCode", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    data = await apiService.getAbhaQrCode(requestBody)
    return Response(content=data, media_type="image/png")
