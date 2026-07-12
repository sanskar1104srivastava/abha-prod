from __future__ import annotations

from pydantic import BaseModel


class CallbackAckResponse(BaseModel):
    acknowledgement: dict[str, str]
    resp: dict[str, str]
