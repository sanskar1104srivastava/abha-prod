from __future__ import annotations

import base64
import json
from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.constants.errorCodes import ErrorCode
from common.constants.tableNames import TableName
from common.db.dynamoDbService import DynamoDbService
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from modules.abha.requests import (
    AadhaarOtpRequest,
    AadhaarVerifyOtpRequest,
    AbhaAddressSetRequest,
    AbhaLookupRequest,
    AbhaLookupVerifyRequest,
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

# ABDM OTPs are valid for 10 minutes; keep the lookup txn context slightly longer.
LOOKUP_CONTEXT_TTL_SECONDS = 900


class AbhaApiService:
    def __init__(self, abdmClient: AbdmClient | None = None, dbService: DynamoDbService | None = None) -> None:
        self.abdmClient = abdmClient or AbdmClient()
        self.dbService = dbService or DynamoDbService()
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

    async def lookup(self, hospitalId: str, requestBody: AbhaLookupRequest) -> dict[str, Any]:
        """Single-call lookup start: accepts mobile or aadhaar, sends the OTP, returns txnId."""
        if requestBody.mobile:
            loginHint, otpSystem, scope, loginId = "mobile", "abdm", ["abha-login", "mobile-verify"], requestBody.mobile
        else:
            loginHint, otpSystem, scope, loginId = "aadhaar", "aadhaar", ["abha-login", "aadhaar-verify"], requestBody.aadhaar
        encLoginId = await self._encrypt(loginId)
        response = await self.abdmClient.abhaPost(
            "profile/login/request/otp",
            {"scope": scope, "loginHint": loginHint, "loginId": encLoginId, "otpSystem": otpSystem},
        )
        txnId = str(response.get("txnId") or "")
        if not txnId:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM did not return a txnId for the lookup OTP", {"body": response})
        self._saveLookupContext(hospitalId, txnId, loginHint)
        return {"txnId": txnId, "message": str(response.get("message") or "OTP sent")}

    async def lookupVerify(self, hospitalId: str, requestBody: AbhaLookupVerifyRequest) -> dict[str, Any]:
        """Verify the lookup OTP and return the full ABHA profile.

        Mobile lookups return a transfer (T) token from ABDM; it is exchanged for the
        final X-token via profile/login/verify/user — automatically when the mobile has a
        single linked account, otherwise the caller re-invokes with txnId + abhaNumber.
        """
        context = self._loadLookupContext(hospitalId, requestBody.txnId)
        loginHint = str(context.get("loginHint") or "mobile")
        storedTToken = str(context.get("tToken") or "")
        if requestBody.abhaNumber and storedTToken and not requestBody.otp:
            return await self._lookupCompleteWithTToken(hospitalId, requestBody.txnId, storedTToken, requestBody.abhaNumber)
        if not requestBody.otp:
            raise AppError(400, ErrorCode.INVALID_REQUEST, "otp is required")
        scope = ["abha-login", "mobile-verify"] if loginHint == "mobile" else ["abha-login", "aadhaar-verify"]
        encOtp = await self._encrypt(requestBody.otp)
        verifyResponse = await self.abdmClient.abhaPost(
            "profile/login/verify",
            {
                "scope": scope,
                "authData": {"authMethods": ["otp"], "otp": {"txnId": requestBody.txnId, "otpValue": encOtp}},
            },
        )
        token = str(verifyResponse.get("token") or verifyResponse.get("tToken") or "")
        if not token:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM login verify returned no token", {"body": verifyResponse})
        if self._isFinalLoginToken(token):
            return await self._lookupFinish(hospitalId, requestBody.txnId, token)
        accounts = self._extractAccounts(verifyResponse)
        abhaNumber = requestBody.abhaNumber or str(self._jwtPayload(token).get("abhaNumber") or "")
        if not abhaNumber and len(accounts) == 1:
            abhaNumber = self._accountAbhaNumber(accounts[0])
        if abhaNumber:
            return await self._lookupCompleteWithTToken(hospitalId, requestBody.txnId, token, abhaNumber)
        if loginHint == "aadhaar":
            return await self._lookupFinish(hospitalId, requestBody.txnId, token)
        self._saveLookupContext(hospitalId, requestBody.txnId, loginHint, tToken=token)
        return {
            "txnId": requestBody.txnId,
            "accountSelectionRequired": True,
            "accounts": accounts,
            "message": "Multiple ABHA accounts are linked to this mobile. Call this endpoint again with txnId and the chosen abhaNumber (no otp needed).",
        }

    async def _lookupCompleteWithTToken(self, hospitalId: str, txnId: str, tToken: str, abhaNumber: str) -> dict[str, Any]:
        txnForUser = str(self._jwtPayload(tToken).get("txnId") or txnId)
        userResponse = await self.abdmClient.abhaPost(
            "profile/login/verify/user",
            {"ABHANumber": self._formatAbhaNumber(abhaNumber), "txnId": txnForUser},
            extraHeaders={"T-token": f"Bearer {tToken}"},
        )
        xToken = str(userResponse.get("token") or userResponse.get("xToken") or "")
        if not xToken:
            raise AppError(424, ErrorCode.UPSTREAM_ERROR, "ABDM account selection returned no token", {"body": userResponse})
        return await self._lookupFinish(hospitalId, txnId, xToken)

    async def _lookupFinish(self, hospitalId: str, txnId: str, xToken: str) -> dict[str, Any]:
        profile = await self.abdmClient.abhaGet(
            "profile/account",
            extraHeaders={"X-token": f"Bearer {xToken}"},
        )
        self._deleteLookupContext(hospitalId, txnId)
        return {"txnId": txnId, "xToken": xToken, "profile": profile}

    def _saveLookupContext(self, hospitalId: str, txnId: str, loginHint: str, tToken: str = "") -> None:
        item = {
            **self._lookupContextKey(hospitalId, txnId),
            "loginHint": loginHint,
            "updatedAt": DateTimeUtils.utcnowIso(),
            "expiresAt": DateTimeUtils.epochSeconds() + LOOKUP_CONTEXT_TTL_SECONDS,
        }
        if tToken:
            item["tToken"] = tToken
        self.dbService.putItem(TableName.STATUS_STORE.value, item)

    def _loadLookupContext(self, hospitalId: str, txnId: str) -> dict[str, Any]:
        item = self.dbService.getItem(TableName.STATUS_STORE.value, self._lookupContextKey(hospitalId, txnId), consistentRead=True)
        # DynamoDB TTL deletion is lazy, so expiry is also enforced at read time.
        if not item or int(item.get("expiresAt") or 0) < DateTimeUtils.epochSeconds():
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Unknown or expired lookup txnId; start the lookup again")
        return item

    def _deleteLookupContext(self, hospitalId: str, txnId: str) -> None:
        # Cleanup must never fail a completed lookup; the row expires via expiresAt anyway.
        try:
            self.dbService.deleteItem(TableName.STATUS_STORE.value, self._lookupContextKey(hospitalId, txnId))
        except Exception as exc:
            self.logger.logError("deleteLookupContext", exc, txnId=txnId)

    @staticmethod
    def _lookupContextKey(hospitalId: str, txnId: str) -> dict[str, str]:
        return {"pk": f"HOSP#{hospitalId}", "sk": f"ABHALOOKUP#{txnId}"}

    @staticmethod
    def _jwtPayload(token: str) -> dict[str, Any]:
        """Unverified claim extraction for routing only — forged claims just fail on the next ABDM call."""
        if not token or token.count(".") != 2:
            return {}
        try:
            payloadPart = token.split(".")[1]
            padded = payloadPart + "=" * (-len(payloadPart) % 4)
            parsed = json.loads(base64.urlsafe_b64decode(padded))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _isFinalLoginToken(cls, token: str) -> bool:
        """ABDM issues typ=Transfer tokens when account selection is still pending."""
        typ = str(cls._jwtPayload(token).get("typ") or "").strip().lower()
        return bool(typ) and typ != "transfer"

    @staticmethod
    def _extractAccounts(response: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("accounts", "users", "ABHA", "abha"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _accountAbhaNumber(cls, account: dict[str, Any]) -> str:
        value = account.get("ABHANumber") or account.get("abhaNumber") or account.get("healthIdNumber") or account.get("healthId") or ""
        return cls._formatAbhaNumber(str(value))

    @staticmethod
    def _formatAbhaNumber(value: str) -> str:
        digits = str(value or "").strip().replace("-", "").replace(" ", "")
        if len(digits) == 14 and digits.isdigit():
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}-{digits[10:]}"
        return str(value or "").strip()

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
