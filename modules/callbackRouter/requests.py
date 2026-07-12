from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CallbackEnvelope(BaseModel):
    path: str
    headers: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
