from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class OnDiscoverRequest(FlexRequest):
    transactionId: str = Field(min_length=1)
    patient: dict[str, Any] | None = None
    resp: dict[str, Any] = Field(default_factory=dict)


class OnInitRequest(FlexRequest):
    transactionId: str = Field(min_length=1)
    link: dict[str, Any] = Field(default_factory=dict)
    resp: dict[str, Any] = Field(default_factory=dict)


class OnConfirmRequest(FlexRequest):
    transactionId: str = Field(min_length=1)
    patient: dict[str, Any] | None = None
    resp: dict[str, Any] = Field(default_factory=dict)
