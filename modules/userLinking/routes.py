from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.logging.loggingService import LoggingService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.userLinking.apiService import UserLinkingApiService
from modules.userLinking.requests import OnConfirmRequest, OnDiscoverRequest, OnInitRequest

router = APIRouter()
apiService = UserLinkingApiService()
authService = ApiKeyAuthService()
logger = LoggingService("userLinking.routes")


def _authenticate(request: Request) -> None:
    authService.authenticate(dict(request.headers))


@router.post("/v1/user-linking/on-discover")
async def respondDiscovery(request: Request, requestBody: OnDiscoverRequest) -> dict[str, Any]:
    """
    Respond to ABDM patient discovery (HIP → gateway on-discover).

    Call this after your HMS receives a discovery webhook event and identifies
    the matching patient. Supply the patient's care contexts and reference IDs.
    The gateway needs `transactionId` from the original discovery callback and
    `resp.requestId` (the callback's requestId) for correlation.
    """
    _authenticate(request)
    logger.logInput("respondDiscovery", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.respondDiscovery(requestBody)


@router.post("/v1/user-linking/on-init")
async def respondLinkInit(request: Request, requestBody: OnInitRequest) -> dict[str, Any]:
    """
    Respond to ABDM link-init (HIP → gateway on-init).

    Call after HMS receives the link-init webhook. Provide a `link.referenceNumber`
    (your OTP reference) so ABDM can send OTP to the patient. The `link.authenticators`
    array specifies OTP mode.
    """
    _authenticate(request)
    logger.logInput("respondLinkInit", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.respondLinkInit(requestBody)


@router.post("/v1/user-linking/on-confirm")
async def respondLinkConfirm(request: Request, requestBody: OnConfirmRequest) -> dict[str, Any]:
    """
    Confirm care context linking (HIP → gateway on-confirm).

    Call after HMS receives the link-confirm webhook (after patient enters OTP).
    Provide the final `patient` object with linked care contexts.
    """
    _authenticate(request)
    logger.logInput("respondLinkConfirm", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.respondLinkConfirm(requestBody)
