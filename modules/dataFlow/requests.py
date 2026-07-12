from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class DataEntry(FlexibleRequest):
    content: str = Field(min_length=1)
    media: str | None = None
    checksum: str | None = None
    careContextReference: str | None = None


class DataPushRequest(FlexibleRequest):
    transactionId: str = Field(min_length=1)
    entries: list[DataEntry] = Field(default_factory=list)
    keyMaterial: dict[str, Any] = Field(default_factory=dict)
    pageNumber: int = 1
    pageCount: int = 1
    consentId: str | None = None


class DataFlowJobRequest(FlexibleRequest):
    jobId: str
    jobType: str
    hospitalId: str
    trackingId: str
    callbackId: str | None = None
    callbackPath: str | None = None
    correlationIds: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
