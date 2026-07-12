from __future__ import annotations

from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
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


class AbhaApiService:
    def __init__(self, abdmClient: AbdmClient | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.logger = LoggingService("abha.apiService")

    async def _encrypt(self, plainText: str) -> str:
        publicKeyB64 = await self.abdmClient.fetchAbhaPublicKey()
        if not publicKeyB64:
            raise AppError(500, ErrorCode.UPSTREAM_ERROR, "Could not fetch ABDM public key")
        return AbdmCryptoService.rsaEncryptOaep(plainText, publicKeyB64)

    async def enrollAadhaarRequestOtp(self, requestBody: AadhaarOtpRequest) -> dict[str, Any]:
        encAadhaar = await self._encrypt(requestBody.aadhaar)
        payload: dict[str, Any] = {
            "scope": ["abha-enrol"],
            "loginHint": "aadhaar",
            "loginId": encAadhaar,
            "otpSystem": "aadhaar",
        }
        if requestBody.txnId:
            payload["txnId"] = requestBody.txnId
        return await self.abdmClient.abhaPost("enrollment/request/otp", payload)

    async def enrollAadhaarVerifyOtp(self, requestBody: AadhaarVerifyOtpRequest) -> dict[str, Any]:
        encOtp = await self._encrypt(requestBody.otp)
        otpData: dict[str, Any] = {"txnId": requestBody.txnId, "otpValue": encOtp}
        if requestBody.mobile:
            otpData["mobile"] = requestBody.mobile
        return await self.abdmClient.abhaPost(
            "enrollment/enrol/byAadhaar",
            {
                "authData": {"authMethods": ["otp"], "otp": otpData},
                "consent": {"code": "abha-enrollment", "version": "1.4"},
            },
        )

    async def enrollMobileRequestOtp(self, requestBody: MobileOtpRequest) -> dict[str, Any]:
        encMobile = await self._encrypt(requestBody.mobile)
        payload: dict[str, Any] = {
            "scope": ["abha-enrol", "mobile-verify"],
            "loginHint": "mobile",
            "loginId": encMobile,
            "otpSystem": "abdm",
        }
        if requestBody.txnId:
            payload["txnId"] = requestBody.txnId
        return await self.abdmClient.abhaPost("enrollment/request/otp", payload)

    async def enrollMobileVerifyOtp(self, requestBody: MobileVerifyOtpRequest) -> dict[str, Any]:
        encOtp = await self._encrypt(requestBody.otp)
        return await self.abdmClient.abhaPost(
            "enrollment/auth/byAbdm",
            {
                "scope": ["abha-enrol", "mobile-verify"],
                "authData": {
                    "authMethods": ["otp"],
                    "otp": {
                        "timeStamp": DateTimeUtils.utcnowIso(),
                        "txnId": requestBody.txnId,
                        "otpValue": encOtp,
                    },
                },
            },
        )

    async def getAddressSuggestions(self, requestBody: AbhaSuggestionsRequest) -> dict[str, Any]:
        return await self.abdmClient.abhaGet(
            "enrollment/enrol/suggestion",
            extraHeaders={"Transaction_Id": requestBody.txnId},
        )

    async def setAbhaAddress(self, requestBody: AbhaAddressSetRequest) -> dict[str, Any]:
        return await self.abdmClient.abhaPost(
            "enrollment/enrol/abha-address",
            {"txnId": requestBody.txnId, "abhaAddress": requestBody.abhaAddress, "preferred": 1},
        )

    async def searchByMobile(self, requestBody: AbhaMobileSearchRequest) -> dict[str, Any]:
        encMobile = await self._encrypt(requestBody.mobile)
        return await self.abdmClient.abhaPost(
            "profile/account/abha/search",
            {"scope": ["search-abha"], "mobile": encMobile},
        )

    async def searchByAbhaNumber(self, requestBody: AbhaNumberSearchRequest) -> dict[str, Any]:
        return await self.abdmClient.abhaPost(
            "profile/login/search",
            {"ABHANumber": requestBody.abhaNumber.replace("-", "")},
        )

    async def phrSearch(self, requestBody: PhrSearchRequest) -> dict[str, Any]:
        return await self.abdmClient.abhaPost(
            "phr/web/login/abha/search",
            {"abhaAddress": requestBody.abhaAddress},
        )

    async def phrSendOtp(self, requestBody: PhrOtpRequest) -> dict[str, Any]:
        encAddress = await self._encrypt(requestBody.abhaAddress)
        payload: dict[str, Any] = {
            "scope": ["abha-login", "abha-address-verify"],
            "loginHint": "abha-address",
            "loginId": encAddress,
            "otpSystem": requestBody.otpSystem,
        }
        if requestBody.txnId:
            payload["txnId"] = requestBody.txnId
        return await self.abdmClient.abhaPost("phr/web/login/abha/request/otp", payload)

    async def phrVerifyOtp(self, requestBody: PhrVerifyOtpRequest) -> dict[str, Any]:
        encOtp = await self._encrypt(requestBody.otp)
        return await self.abdmClient.abhaPost(
            "phr/web/login/abha/verify",
            {
                "scope": ["abha-login", "abha-address-verify"],
                "authData": {
                    "authMethods": ["otp"],
                    "otp": {"txnId": requestBody.txnId, "otpValue": encOtp},
                },
            },
        )

    async def getProfileDetails(self, requestBody: AbhaProfileRequest) -> dict[str, Any]:
        return await self.abdmClient.abhaGet(
            "profile/account",
            extraHeaders={"X-token": f"Bearer {requestBody.xToken}"},
        )

    async def getAbhaCard(self, requestBody: AbhaProfileRequest) -> bytes:
        return await self.abdmClient.abhaGetBinary("profile/account/abha-card", xToken=requestBody.xToken)

    async def getAbhaQrCode(self, requestBody: AbhaProfileRequest) -> bytes:
        return await self.abdmClient.abhaGetBinary("profile/account/qrCode", xToken=requestBody.xToken)
