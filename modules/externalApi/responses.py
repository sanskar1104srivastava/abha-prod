from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AcceptedResponse(BaseModel):
    trackingId: str
    requestId: str
    status: str = "accepted"


class StatusResponse(BaseModel):
    trackingId: str
    status: str
    eventType: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResultResponse(BaseModel):
    trackingId: str
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
