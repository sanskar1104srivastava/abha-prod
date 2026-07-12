from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookEventRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    eventId: str
    hospitalId: str
    trackingId: str
    eventType: str
    callbackId: str | None = None
    callbackPath: str | None = None
    correlationIds: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    webhookUrl: HttpUrl | None = None
