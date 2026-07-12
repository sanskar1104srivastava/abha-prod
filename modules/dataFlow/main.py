import asyncio
from typing import Any

from mangum import Mangum

from common.http.fastApiFactory import createFastApiApp
from modules.dataFlow.apiService import DataFlowApiService
from modules.dataFlow.routes import router

app = createFastApiApp("sahai-production-data-flow", lambda fastApiApp: fastApiApp.include_router(router))

asgiHandler = Mangum(app)


async def handleQueueEvent(records: list[dict[str, Any]]) -> dict[str, Any]:
    return await DataFlowApiService().handleQueueRecords(records)


def ensureEventLoop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if isinstance(event.get("Records"), list):
        return asyncio.run(handleQueueEvent(event["Records"]))
    ensureEventLoop()
    return asgiHandler(event, context)
