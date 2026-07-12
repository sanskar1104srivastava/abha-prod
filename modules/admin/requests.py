from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetGatewayTokenRequest(StrictRequest):
    token: str = Field(min_length=10, description="ABDM gateway Bearer token obtained from ABDM sandbox portal or Postman")
    expiresIn: int = Field(default=1800, ge=60, le=86400, description="Token lifetime in seconds (default 30 min)")


class CreateCustomerRequest(StrictRequest):
    loginId: str = Field(min_length=3, max_length=128, description="Unique login identifier — use email or slug")
    password: str = Field(min_length=8, max_length=256)
    hospitalName: str = Field(min_length=1, max_length=255)
    hipId: str = Field(min_length=1, max_length=64, description="ABDM HIP ID assigned to this hospital")
    hiuId: str = Field(min_length=1, max_length=64, description="ABDM HIU ID assigned to this hospital")
    webhookUrl: str | None = Field(default=None, max_length=2048)
    webhookSecret: str | None = Field(default=None, max_length=256)
    dataPushUrl: str | None = Field(default=None, max_length=2048, description="HTTPS URL where the HIP pushes encrypted health information for this hospital")
    setupBridge: bool = Field(default=True, description="Auto-register callback URL + bridge services with ABDM")
    facilityId: str | None = Field(default=None, max_length=64, description="ABDM facility ID for bridge registration (defaults to hipId)")
    facilityName: str | None = Field(default=None, max_length=255, description="Facility display name for bridge registration (defaults to hospitalName)")
    hrp: list[dict[str, Any]] = Field(default_factory=list, description="Custom HRP service objects. If empty, auto-generated from hipId/hiuId.")
