import asyncio
from typing import Any

from modules.webhookDispatcher.apiService import WebhookDispatcherApiService

service = WebhookDispatcherApiService()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return asyncio.run(service.handleQueueRecords(event.get("Records") or []))
