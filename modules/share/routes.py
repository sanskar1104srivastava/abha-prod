from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.logging.loggingService import LoggingService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.share.apiService import ShareApiService
from modules.share.requests import ShareOnShareRequest

router = APIRouter()
apiService = ShareApiService()
authService = ApiKeyAuthService()
logger = LoggingService("share.routes")


def _authenticate(request: Request) -> None:
    authService.authenticate(dict(request.headers))


@router.post("/v1/share/on-share")
async def onShare(request: Request, requestBody: ShareOnShareRequest) -> dict[str, Any]:
    """
    HIP acknowledges a patient profile share (scan-and-share flow).

    When a patient scans the facility's QR code, ABDM sends the patient profile
    to the callback URL. After processing, call this to confirm receipt and
    optionally return a token number to the patient via the ABDM app.
    """
    _authenticate(request)
    logger.logInput("onShare", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.onShare(requestBody)
