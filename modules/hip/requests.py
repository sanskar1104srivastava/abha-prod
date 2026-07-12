from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FetchModesRequest(StrictRequest):
    """Fetch available auth modes for a patient at this HIP."""
    abhaAddress: str = Field(min_length=1, max_length=255)
    purpose: str = Field(default="LINK")


class OtpInitRequest(StrictRequest):
    """Initiate OTP-based authentication for HIP linking."""
    abhaAddress: str = Field(min_length=1, max_length=255)
    authMode: str = Field(default="MOBILE_OTP")
    purpose: str = Field(default="LINK")


class OtpConfirmRequest(StrictRequest):
    """Confirm OTP to complete HIP auth; returns linkToken on success."""
    transactionId: str = Field(min_length=1)
    otp: str = Field(min_length=4, max_length=8)


class CareContextNotifyRequest(StrictRequest):
    """Notify ABDM about a newly linked care context."""
    abhaAddress: str = Field(min_length=1, max_length=255)
    patientReference: str = Field(min_length=1, max_length=255)
    careContextReference: str = Field(min_length=1, max_length=255)
    hiTypes: list[str] = Field(default_factory=list)
    linkToken: str = Field(min_length=1, description="X-link-token from the linking flow")


class ConsentOnNotifyRequest(StrictRequest):
    """HIP acknowledges a consent notification received from ABDM."""
    consentId: str = Field(min_length=1)
    status: str = Field(default="OK")
    requestId: str = Field(min_length=1, description="requestId from the ABDM consent notification")


class HealthInfoOnRequestRequest(StrictRequest):
    """HIP acknowledges a health-information request from ABDM."""
    transactionId: str = Field(min_length=1)
    sessionStatus: str = Field(default="ACKNOWLEDGED")
    requestId: str = Field(min_length=1, description="requestId from the ABDM health-info callback")
    careContextReferences: list[str] = Field(default_factory=list)


class SmsNotifyRequest(StrictRequest):
    """Send a deep-link SMS so a patient can link care contexts via the ABDM app."""
    phoneNo: str = Field(min_length=10, max_length=15, description="Patient mobile with country code, e.g. +919876543210")
