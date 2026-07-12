from __future__ import annotations

import json
import os
import secrets
from typing import Any

import httpx

from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.security.webhookSignatureService import WebhookSignatureService
from common.utils.hashUtils import HashUtils
from common.utils.networkUtils import NetworkUtils
from modules.auth.dbService import AuthDbService
from modules.auth.requests import HospitalLoginRequest, HospitalRegisterRequest, UpdateDataPushRequest, UpdateWebhookRequest
from modules.auth.responses import AuthTokenResponse, HospitalProfileResponse, LoginResponse


class AuthService:
    def __init__(self, dbService: AuthDbService | None = None) -> None:
        self.db = dbService or AuthDbService()
        self.logger = LoggingService("auth")

    # ── Register ─────────────────────────────────────────────────────────────

    def register(self, request: HospitalRegisterRequest) -> dict[str, Any]:
        loginId = request.loginId.lower().strip()

        existing = self.db.getLoginRef(loginId)
        if existing:
            raise AppError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "A hospital with this loginId already exists")

        hospitalId = self._newHospitalId()
        passwordHash = HashUtils.sha256Text(request.password)
        rawKey, apiKeyHash = self._generateApiKey()
        environment = os.environ.get("appEnv", "dev")
        dataPushUrl = NetworkUtils.validateExternalHttpsUrl(request.dataPushUrl) if request.dataPushUrl else None

        self.db.createHospital(
            hospitalId=hospitalId,
            loginId=loginId,
            passwordHash=passwordHash,
            hospitalName=request.hospitalName.strip(),
            hipId=request.hipId or "",
            hiuId=request.hiuId or "",
            webhookUrl=request.webhookUrl,
            webhookSecret=request.webhookSecret,
            activeKeyHash=apiKeyHash,
            environment=environment,
            dataPushUrl=dataPushUrl,
        )
        self.db.putApiKey(apiKeyHash, hospitalId, request.hipId or "", request.hiuId or "", environment)

        self.logger.logProcess("hospitalRegistered", hospitalId=hospitalId, loginId=loginId)

        return AuthTokenResponse(
            hospitalId=hospitalId,
            loginId=loginId,
            hospitalName=request.hospitalName.strip(),
            apiKey=rawKey,
            environment=environment,
            message="Hospital registered. Save your API key — it will not be shown again.",
        ).model_dump(mode="json")

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, request: HospitalLoginRequest) -> dict[str, Any]:
        loginId = request.loginId.lower().strip()

        ref = self.db.getLoginRef(loginId)
        if not ref:
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Invalid loginId or password")

        hospitalId = str(ref["hospitalId"])
        profile = self.db.getProfile(hospitalId)
        if not profile or str(profile.get("status") or "") != "active":
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Hospital account is inactive or not found")

        if profile.get("passwordHash") != HashUtils.sha256Text(request.password):
            raise AppError(401, ErrorCode.NOT_AUTHENTICATED, "Invalid loginId or password")

        self.logger.logProcess("hospitalLogin", hospitalId=hospitalId, loginId=loginId)

        return LoginResponse(
            hospitalId=hospitalId,
            loginId=loginId,
            hospitalName=str(profile.get("hospitalName") or ""),
            environment=str(profile.get("environment") or "dev"),
            message="Login successful. Use your existing API key for all requests. To issue a new key call POST /v1/auth/rotate-key.",
        ).model_dump(mode="json")

    # ── Rotate API key ────────────────────────────────────────────────────────

    def rotateKey(self, hospitalId: str) -> dict[str, Any]:
        profile = self.db.getProfile(hospitalId)
        if not profile:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Hospital not found")

        oldKeyHash = str(profile.get("activeKeyHash") or "")
        rawKey, apiKeyHash = self._generateApiKey()

        self.db.putApiKey(apiKeyHash, hospitalId, str(profile.get("hipId") or ""), str(profile.get("hiuId") or ""), str(profile.get("environment") or "dev"))
        self.db.updateActiveKeyHash(hospitalId, apiKeyHash)
        self.db.deactivateApiKey(oldKeyHash)

        self.logger.logProcess("apiKeyRotated", hospitalId=hospitalId)

        return AuthTokenResponse(
            hospitalId=hospitalId,
            loginId=str(profile.get("loginId") or ""),
            hospitalName=str(profile.get("hospitalName") or ""),
            apiKey=rawKey,
            environment=str(profile.get("environment") or "dev"),
            message="API key rotated. Save your new key — the previous key has been revoked.",
        ).model_dump(mode="json")

    # ── Profile ───────────────────────────────────────────────────────────────

    def getProfile(self, hospitalId: str) -> dict[str, Any]:
        profile = self.db.getProfile(hospitalId)
        if not profile:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Hospital not found")
        return HospitalProfileResponse(
            hospitalId=hospitalId,
            loginId=str(profile.get("loginId") or ""),
            hospitalName=str(profile.get("hospitalName") or ""),
            environment=str(profile.get("environment") or "dev"),
            hipId=str(profile.get("hipId") or ""),
            hiuId=str(profile.get("hiuId") or ""),
            webhookUrl=str(profile.get("webhookUrl") or "") or None,
            dataPushUrl=str(profile.get("dataPushUrl") or "") or None,
            createdAt=str(profile.get("createdAt") or ""),
            updatedAt=str(profile.get("updatedAt") or "") or None,
        ).model_dump(mode="json")

    # ── Webhook management ────────────────────────────────────────────────────

    def updateWebhook(self, hospitalId: str, request: UpdateWebhookRequest) -> dict[str, Any]:
        webhookUrl = NetworkUtils.validateExternalHttpsUrl(request.webhookUrl)
        self.db.updateWebhook(hospitalId, webhookUrl, request.webhookSecret)
        self.logger.logProcess("webhookUpdated", hospitalId=hospitalId)
        return {"status": "ok", "webhookUrl": webhookUrl}

    def updateDataPush(self, hospitalId: str, request: UpdateDataPushRequest) -> dict[str, Any]:
        profile = self.db.getProfile(hospitalId)
        if not profile:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Hospital not found")
        dataPushUrl = NetworkUtils.validateExternalHttpsUrl(request.dataPushUrl)
        self.db.updateDataPushUrl(hospitalId, dataPushUrl)
        self.logger.logProcess("dataPushUrlUpdated", hospitalId=hospitalId)
        return {"status": "ok", "dataPushUrl": dataPushUrl}

    async def testWebhookEndpoint(self, hospitalId: str) -> dict[str, Any]:
        profile = self.db.getProfile(hospitalId)
        if not profile:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Hospital not found")
        webhookUrl = str(profile.get("webhookUrl") or "").strip()
        webhookSecret = str(profile.get("webhookSecret") or "").strip()
        if not webhookUrl:
            raise AppError(400, ErrorCode.INVALID_REQUEST, "No webhook URL configured. Call PUT /v1/webhook-endpoint first.")
        if not webhookSecret:
            raise AppError(400, ErrorCode.INVALID_REQUEST, "No webhook secret configured. Call PUT /v1/webhook-endpoint first.")
        try:
            webhookUrl = NetworkUtils.validateExternalHttpsUrl(webhookUrl)
        except Exception as exc:
            raise AppError(400, ErrorCode.INVALID_REQUEST, f"Stored webhook URL is invalid: {exc}") from exc
        testRequestId = "test-" + secrets.token_hex(8)
        body: dict[str, Any] = {
            "requestId": testRequestId,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "testMessage": "Test callback from Sahai. Your webhook endpoint is reachable and the signature is valid.",
        }
        bodyText = json.dumps(body, separators=(",", ":"))
        headers = {
            "Content-Type": "application/json",
            "X-Abdm-Path": "/sahai/test",
            "X-Abdm-Signature": WebhookSignatureService.signPayload(webhookSecret, bodyText),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(webhookUrl, content=bodyText, headers=headers)
            return {
                "status": "delivered" if response.status_code < 400 else "failed",
                "statusCode": response.status_code,
                "requestId": testRequestId,
            }
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AppError(502, ErrorCode.UPSTREAM_ERROR, f"Webhook delivery failed: {exc}") from exc

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _generateApiKey() -> tuple[str, str]:
        raw = "sahai-" + secrets.token_urlsafe(32)
        return raw, HashUtils.sha256Text(raw)

    @staticmethod
    def _newHospitalId() -> str:
        return "HOSP-" + secrets.token_hex(8).upper()
