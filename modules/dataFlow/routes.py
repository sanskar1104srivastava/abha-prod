from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status

from common.logging.loggingService import LoggingService
from modules.dataFlow.apiService import DataFlowApiService
from modules.dataFlow.requests import DataFlowJobRequest, DataPushRequest

router = APIRouter()
apiService = DataFlowApiService()
logger = LoggingService("dataFlow.routes")


@router.post("/data", status_code=status.HTTP_202_ACCEPTED)
async def dataRoot(request: Request, requestBody: DataPushRequest) -> dict[str, Any]:
    logger.logInput("dataPush", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.handleInboundDataPush("/data", dict(request.headers), requestBody)


@router.api_route("/data/{dataPath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], status_code=status.HTTP_202_ACCEPTED)
async def dataProxy(request: Request, dataPath: str) -> dict[str, Any]:
    body = await request.json()
    requestBody = DataPushRequest.model_validate(body)
    logger.logInput("dataProxy", headers=dict(request.headers), body={"path": f"/data/{dataPath}", **requestBody.model_dump(mode="json")})
    return await apiService.handleInboundDataPush(f"/data/{dataPath}", dict(request.headers), requestBody)


@router.post("/internal/data-flow/jobs", status_code=status.HTTP_202_ACCEPTED)
async def runDataFlowJob(requestBody: DataFlowJobRequest) -> dict[str, Any]:
    logger.logInput("runDataFlowJob", body=requestBody.model_dump(mode="json"))
    return await apiService.handleJob(requestBody)
