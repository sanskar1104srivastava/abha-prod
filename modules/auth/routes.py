from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.logging.loggingService import LoggingService
from common.security.adminAuthService import AdminAuthService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.auth.apiService import AuthService
from modules.auth.requests import HospitalLoginRequest, HospitalRegisterRequest, UpdateDataPushRequest, UpdateWebhookRequest

router = APIRouter()
authService = AuthService()
apiKeyAuth = ApiKeyAuthService()
adminAuth = AdminAuthService()
logger = LoggingService("auth.routes")


def _authenticate(request: Request) -> dict[str, Any]:
    return apiKeyAuth.authenticate(dict(request.headers))


def _authenticateAdmin(request: Request) -> None:
    adminAuth.authenticate(dict(request.headers))


# ── Admin-only: hospital provisioning ────────────────────────────────────────

@router.post("/v1/auth/register", status_code=201)
async def register(request: Request, requestBody: HospitalRegisterRequest) -> dict[str, Any]:
    """
    Create a new hospital account (admin-only).

    Prefer POST /v1/admin/customers — it creates the account AND auto-registers
    the ABDM bridge. Use this endpoint only when bridge setup is not needed.
    Requires: Authorization: Bearer <admin-key>
    """
    _authenticateAdmin(request)
    logger.logInput("register", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return authService.register(requestBody)


# ── Customer-facing: credentials ─────────────────────────────────────────────

@router.post("/v1/auth/login")
async def login(requestBody: HospitalLoginRequest) -> dict[str, Any]:
    """
    Verify credentials (loginId + password). Does not issue or rotate the API key.
    Use the API key issued at registration for all requests: Authorization: Bearer <apiKey>
    To rotate the key explicitly, call POST /v1/auth/rotate-key.
    """
    logger.logInput("login", body=requestBody.model_dump(mode="json"))
    return authService.login(requestBody)


@router.post("/v1/auth/rotate-key")
async def rotateKey(request: Request) -> dict[str, Any]:
    """Issue a new API key and revoke the current one."""
    context = _authenticate(request)
    logger.logInput("rotateKey", headers=dict(request.headers), hospitalId=context["hospitalId"])
    return authService.rotateKey(context["hospitalId"])


@router.get("/v1/auth/me")
async def getProfile(request: Request) -> dict[str, Any]:
    """Return the authenticated hospital profile."""
    context = _authenticate(request)
    logger.logInput("getProfile", headers=dict(request.headers), hospitalId=context["hospitalId"])
    return authService.getProfile(context["hospitalId"])


# ── Customer-facing: webhook management ──────────────────────────────────────

@router.put("/v1/webhook-endpoint")
async def updateWebhookEndpoint(request: Request, requestBody: UpdateWebhookRequest) -> dict[str, Any]:
    """
    Set or update the webhook endpoint for ABDM event notifications.

    Sahai forwards raw ABDM callbacks signed with HMAC-SHA256 using webhookSecret.
    Verify the X-Abdm-Signature header on every incoming request to confirm authenticity.
    Run POST /v1/webhook-endpoint/test after this to confirm delivery works.
    """
    context = _authenticate(request)
    logger.logInput("updateWebhookEndpoint", headers=dict(request.headers), body=requestBody.model_dump(mode="json"), hospitalId=context["hospitalId"])
    return authService.updateWebhook(context["hospitalId"], requestBody)


@router.put("/v1/data-push-endpoint")
async def updateDataPushEndpoint(request: Request, requestBody: UpdateDataPushRequest) -> dict[str, Any]:
    """
    Set or update the data-push endpoint for HIP health-information delivery.

    When configured, health-information requests instruct the HIP to push
    encrypted FHIR data directly to this URL instead of Sahai's own /data
    endpoint. Decrypt the received payload with POST /v1/health-information/decrypt —
    the ECDH keys never leave Sahai.
    """
    context = _authenticate(request)
    logger.logInput("updateDataPushEndpoint", headers=dict(request.headers), body=requestBody.model_dump(mode="json"), hospitalId=context["hospitalId"])
    return authService.updateDataPush(context["hospitalId"], requestBody)


@router.post("/v1/webhook-endpoint/test")
async def testWebhookEndpoint(request: Request) -> dict[str, Any]:
    """
    Send a TEST event to the configured webhook URL.

    Confirms the endpoint is reachable and the signature is verifiable.
    Returns the HTTP status code received from the webhook server.
    """
    context = _authenticate(request)
    logger.logInput("testWebhookEndpoint", headers=dict(request.headers), hospitalId=context["hospitalId"])
    return await authService.testWebhookEndpoint(context["hospitalId"])
