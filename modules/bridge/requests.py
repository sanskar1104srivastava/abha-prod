from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateCallbackUrlRequest(StrictRequest):
    """Update the HIP/HIU callback URL registered with the ABDM gateway."""
    callbackUrl: HttpUrl = Field(description="The HTTPS URL where ABDM will send callbacks")


class BridgeService(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(description="ABDM facility/provider ID")
    name: str = Field(description="Display name of the service")
    type: str = Field(description="Service type: HIP | HIU | HIP-HIU")
    endpoints: list[dict[str, Any]] = Field(default_factory=list)


class RegisterBridgeServicesRequest(StrictRequest):
    facilityId: str = Field(min_length=1)
    facilityName: str = Field(min_length=1)
    hrp: list[dict[str, Any]] = Field(description="List of HRP (Health Record Provider) service objects")


class SmsNotifyRequest(StrictRequest):
    """Send a deep-link SMS to a patient's mobile so they can link care contexts via ABDM app."""
    phoneNo: str = Field(min_length=10, max_length=15, description="Patient mobile number with country code prefix (e.g. +919876543210)")
