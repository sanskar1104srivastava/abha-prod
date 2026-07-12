from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CareContextItem(BaseModel):
    reference: str = Field(min_length=1, max_length=255)
    display: str = Field(min_length=1, max_length=255)
    hiTypes: list[str] = Field(default_factory=list)
    clinicalPayload: dict[str, Any] = Field(default_factory=dict)
    documentData: str | None = None
    documentTitle: str | None = None
    documentContentType: str | None = None


class LinkTokenRequest(StrictRequest):
    hipId: str = Field(min_length=1, max_length=64)
    abhaAddress: str = Field(min_length=1, max_length=255)
    abhaNumber: str | None = Field(default=None, max_length=32)
    patientReference: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    gender: str | None = Field(default=None, max_length=32)
    yearOfBirth: int | None = Field(default=None, ge=1900, le=2100)
    purpose: str = Field(default="LINK_CARE_CONTEXT", max_length=128)


class CareContextLinkRequest(StrictRequest):
    hipId: str = Field(min_length=1, max_length=64)
    abhaAddress: str = Field(min_length=1, max_length=255)
    abhaNumber: str | None = Field(default=None, max_length=32)
    patientReference: str = Field(min_length=1, max_length=128)
    linkToken: str | None = Field(default=None, max_length=2048)
    careContexts: list[CareContextItem] = Field(min_length=1)


class ConsentRequester(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Name of the requesting clinician or system")
    type: str = Field(min_length=1, max_length=64, description="Identifier type, e.g. REGNO, HPR")
    value: str = Field(min_length=1, max_length=128, description="Identifier value, e.g. registration number")
    system: str = Field(min_length=1, max_length=255, description="Identifier system/issuing authority URI")


class ConsentRequest(StrictRequest):
    abhaAddress: str = Field(min_length=1, max_length=255)
    patientReference: str = Field(min_length=1, max_length=128, description="Hospital's own patient identifier for webhook/decrypt correlation")
    hiuId: str | None = Field(default=None, max_length=64, description="HIU ID for this request; falls back to the HIU ID registered with your API key")
    purpose: dict[str, Any]
    requester: ConsentRequester
    hiTypes: list[str] = Field(min_length=1)
    dateRange: dict[str, Any]
    permission: dict[str, Any]

    @field_validator("purpose")
    @classmethod
    def validatePurpose(cls, value: dict[str, Any]) -> dict[str, Any]:
        # ABDM rejects consent-init when any of these is blank (e.g. "Invalid consent purpose refURI"),
        # so fail fast here instead of a silent dispatchFailed later
        for key in ("text", "code", "refUri"):
            if not str(value.get(key) or "").strip():
                raise ValueError(f"purpose.{key} must not be empty — ABDM rejects consent requests without it")
        return value


class HealthInformationRequest(StrictRequest):
    consentId: str = Field(min_length=1, max_length=255)
    hiuId: str | None = Field(default=None, max_length=64, description="HIU ID for this request; falls back to the HIU ID registered with your API key")
    dateRange: dict[str, Any]
    dataPushUrl: HttpUrl | None = None
    transactionId: str | None = Field(default=None, max_length=255)
    abhaAddress: str | None = Field(default=None, max_length=255)
    patientReference: str | None = Field(default=None, max_length=128)
    consentRequestId: str | None = Field(default=None, max_length=255)
    consentTrackingId: str | None = Field(default=None, max_length=255)
    hiTypes: list[str] = Field(default_factory=list)


class EncryptedDataEntry(BaseModel):
    content: str = Field(min_length=1, description="Base64 ciphertext exactly as received from the HIP")
    media: str | None = Field(default=None, max_length=128)
    checksum: str | None = Field(default=None, max_length=512)
    careContextReference: str | None = Field(default=None, max_length=255)


class HealthInformationDecryptRequest(StrictRequest):
    """Decrypt an ABDM data push that the HIP delivered straight to the hospital's
    own dataPushUrl. Pass the received payload through unchanged — the ECDH key
    session is looked up on our side and never leaves this backend."""
    transactionId: str = Field(min_length=1, max_length=255)
    consentId: str | None = Field(default=None, max_length=255)
    entries: list[EncryptedDataEntry] = Field(min_length=1)
    keyMaterial: dict[str, Any] = Field(description="keyMaterial object from the HIP's push (sender public key + nonce)")


class ConsentStatusRequest(StrictRequest):
    """Check the current status of a consent request with ABDM."""
    consentRequestId: str = Field(min_length=1, max_length=255)
    hiuId: str | None = Field(default=None, max_length=64, description="HIU ID for this request; falls back to the HIU ID registered with your API key")


class ConsentFetchRequest(StrictRequest):
    """Fetch full consent artefact details from ABDM by consent artefact ID."""
    consentId: str = Field(min_length=1, max_length=255)
    hiuId: str | None = Field(default=None, max_length=64, description="HIU ID for this request; falls back to the HIU ID registered with your API key")
