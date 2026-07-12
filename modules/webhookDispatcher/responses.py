from __future__ import annotations

from pydantic import BaseModel


class WebhookDeliveryResponse(BaseModel):
    eventId: str
    status: str
    statusCode: int | None = None
    retryable: bool = False
    message: str = ""
