from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request, status

from common.logging.loggingService import LoggingService
from modules.callbackRouter.apiService import CallbackRouterApiService

router = APIRouter()
apiService = CallbackRouterApiService()
logger = LoggingService("callbackRouter.routes")


@router.api_route("/callback", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], status_code=status.HTTP_202_ACCEPTED)
async def callbackRoot(request: Request) -> dict[str, Any]:
    return await routeCallback(request, "")


@router.api_route("/callback/{callbackPath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], status_code=status.HTTP_202_ACCEPTED)
async def callbackProxy(request: Request, callbackPath: str) -> dict[str, Any]:
    return await routeCallback(request, callbackPath)


async def routeCallback(request: Request, callbackPath: str) -> dict[str, Any]:
    rawBody = (await request.body()).decode("utf-8")
    try:
        payload = json.loads(rawBody)
        if not isinstance(payload, dict):
            payload = {"payload": payload}
    except Exception:
        payload = {}
    path = f"/callback/{callbackPath}".rstrip("/")
    logger.logInput("callback", headers=dict(request.headers), body={"path": path, **payload})
    return await apiService.handleCallbackAsync(path, dict(request.headers), payload, rawBody)
