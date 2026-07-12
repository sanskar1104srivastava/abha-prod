from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.abdm.abdmClient import AbdmClient
from common.logging.loggingService import LoggingService
from common.security.adminAuthService import AdminAuthService
from modules.admin.apiService import AdminApiService
from modules.admin.requests import CreateCustomerRequest, SetGatewayTokenRequest
from modules.bridge.apiService import BridgeApiService
from modules.bridge.requests import RegisterBridgeServicesRequest, UpdateCallbackUrlRequest

router = APIRouter()
apiService = AdminApiService()
bridgeService = BridgeApiService()
adminAuth = AdminAuthService()
logger = LoggingService("admin.routes")


def _authenticate(request: Request) -> None:
    adminAuth.authenticate(dict(request.headers))


# ── Customer management ───────────────────────────────────────────────────────

@router.post("/v1/admin/customers", status_code=201)
async def createCustomer(request: Request, requestBody: CreateCustomerRequest) -> dict[str, Any]:
    """
    Create a new hospital customer account.

    Automatically generates an API key and (by default) registers the ABDM bridge
    callback URL and bridge services. The raw API key is returned once — save it.
    """
    _authenticate(request)
    logger.logInput("createCustomer", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.createCustomer(requestBody)


# ── Bridge management (operator-only) ────────────────────────────────────────

@router.patch("/v1/admin/bridge/callback-url")
async def updateCallbackUrl(request: Request, requestBody: UpdateCallbackUrlRequest) -> dict[str, Any]:
    """Update the ABDM gateway callback URL for this bridge. Run once per environment."""
    _authenticate(request)
    logger.logInput("updateCallbackUrl", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await bridgeService.updateCallbackUrl(requestBody)


@router.post("/v1/admin/bridge/register-services")
async def registerBridgeServices(request: Request, requestBody: RegisterBridgeServicesRequest) -> dict[str, Any]:
    """Register or update HIP/HIU services in the ABDM facility registry."""
    _authenticate(request)
    logger.logInput("registerBridgeServices", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await bridgeService.registerBridgeServices(requestBody)


@router.get("/v1/admin/bridge/services")
async def getBridgeServices(request: Request) -> dict[str, Any]:
    """List all services registered under this bridge with the ABDM gateway."""
    _authenticate(request)
    logger.logInput("getBridgeServices", headers=dict(request.headers))
    return await bridgeService.getBridgeServices()


# ── ABDM token management ─────────────────────────────────────────────────────

@router.post("/v1/admin/abdm/test-token")
async def testAbdmToken(request: Request) -> dict[str, Any]:
    """
    Diagnostic: attempt a live ABDM gateway session token fetch and return full detail.

    Returns the HTTP status, URL, timestamp used, and response body so you can
    verify the credentials and WAF headers are correct without checking CloudWatch.
    If the fetch succeeds, the token is cached immediately for subsequent requests.
    """
    _authenticate(request)
    logger.logInput("testAbdmToken", headers=dict(request.headers))
    client = AbdmClient()
    return await client.testTokenFetch()


@router.put("/v1/admin/abdm/gateway-token")
async def setAbdmGatewayToken(request: Request, requestBody: SetGatewayTokenRequest) -> dict[str, Any]:
    """
    Manually inject an ABDM gateway token for this Lambda container.

    Use when auto-fetch is blocked (e.g., ABDM sandbox WAF issue). Obtain a valid
    token via the ABDM sandbox portal or Postman, then set it here. The token is
    cached in-memory and used for all subsequent ABDM calls until it expires.
    """
    _authenticate(request)
    logger.logInput("setAbdmGatewayToken", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    AbdmClient.setGatewayToken(requestBody.token, requestBody.expiresIn)
    return {"status": "ok", "expiresIn": requestBody.expiresIn}
