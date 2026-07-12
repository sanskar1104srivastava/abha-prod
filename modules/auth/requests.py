from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HospitalRegisterRequest(StrictRequest):
    loginId: str = Field(min_length=3, max_length=128, description="Unique login identifier — use email")
    password: str = Field(min_length=8, max_length=256)
    hospitalName: str = Field(min_length=1, max_length=255)
    hipId: str | None = Field(default=None, max_length=64, description="ABDM HIP ID assigned to this hospital")
    hiuId: str | None = Field(default=None, max_length=64, description="ABDM HIU ID assigned to this hospital")
    webhookUrl: str | None = Field(default=None, max_length=2048, description="HTTPS URL to receive event notifications")
    webhookSecret: str | None = Field(default=None, max_length=256, description="Secret for HMAC-SHA256 webhook signature")
    dataPushUrl: str | None = Field(default=None, max_length=2048, description="HTTPS URL where the HIP pushes encrypted health information for this hospital")


class HospitalLoginRequest(StrictRequest):
    loginId: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class RotateKeyRequest(StrictRequest):
    pass


class UpdateWebhookRequest(StrictRequest):
    webhookUrl: str = Field(min_length=8, max_length=2048, description="HTTPS URL to receive signed webhook events")
    webhookSecret: str = Field(min_length=16, max_length=256, description="Secret used to verify HMAC-SHA256 signature on incoming events")


class UpdateDataPushRequest(StrictRequest):
    dataPushUrl: str = Field(min_length=8, max_length=2048, description="HTTPS URL where the HIP pushes encrypted health information for this hospital")
