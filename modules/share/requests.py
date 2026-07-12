from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShareOnShareRequest(StrictRequest):
    """
    HIP acknowledges a patient profile share (scan-and-share flow).

    Call this after receiving a patient profile via the patientShare webhook
    to confirm the HIP has accepted the profile.
    """
    requestId: str = Field(min_length=1, description="requestId from the ABDM patient-share callback")
    status: str = Field(default="SUCCESS", description="SUCCESS | FAILURE")
    abhaAddress: str = Field(default="", max_length=255)
    tokenNumber: str = Field(default="", max_length=64, description="Token number issued to the patient at the facility")
    expiry: str = Field(default="", max_length=64, description="Token expiry timestamp (ISO 8601)")
    context: list[dict[str, Any]] = Field(default_factory=list, description="Additional context sent back with the on-share")
