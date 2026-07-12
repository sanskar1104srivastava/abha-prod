from __future__ import annotations

from pydantic import BaseModel, Field


class DataAcceptedResponse(BaseModel):
    dataFlowId: str
    trackingId: str | None = None
    status: str
    encryptedCount: int = 0
    decryptedCount: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)


class DataJobResponse(BaseModel):
    jobId: str
    trackingId: str
    status: str
    ackStatus: str | None = None
    pushedEntries: int = 0
    pushStatusCode: int | None = None
    notifyStatus: str | None = None
    cleanupStatus: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
