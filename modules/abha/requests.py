from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AadhaarOtpRequest(StrictRequest):
    aadhaar: str = Field(min_length=12, max_length=12)
    txnId: str = Field(default="")


class AadhaarVerifyOtpRequest(StrictRequest):
    txnId: str = Field(min_length=1)
    otp: str = Field(min_length=4, max_length=8)
    mobile: str = Field(default="")


class MobileOtpRequest(StrictRequest):
    mobile: str = Field(min_length=10, max_length=10)
    txnId: str = Field(default="")


class MobileVerifyOtpRequest(StrictRequest):
    txnId: str = Field(min_length=1)
    otp: str = Field(min_length=4, max_length=8)


class AbhaSuggestionsRequest(StrictRequest):
    txnId: str = Field(min_length=1)


class AbhaAddressSetRequest(StrictRequest):
    txnId: str = Field(min_length=1)
    abhaAddress: str = Field(min_length=1, max_length=100)



class AbhaLookupRequest(StrictRequest):
    """Start an ABHA lookup — send OTP to the mobile or Aadhaar-linked mobile. Exactly one identifier."""
    mobile: str = Field(default="")
    aadhaar: str = Field(default="")

    @model_validator(mode="after")
    def _validateExactlyOneIdentifier(self) -> "AbhaLookupRequest":
        if bool(self.mobile) == bool(self.aadhaar):
            raise ValueError("Provide exactly one of 'mobile' or 'aadhaar'")
        if self.mobile and not (len(self.mobile) == 10 and self.mobile.isdigit()):
            raise ValueError("mobile must be a 10-digit number")
        if self.aadhaar and not (len(self.aadhaar) == 12 and self.aadhaar.isdigit()):
            raise ValueError("aadhaar must be a 12-digit number")
        return self


class AbhaLookupVerifyRequest(StrictRequest):
    """Verify the lookup OTP; returns the full ABHA profile.

    otp is omitted only on the account-selection follow-up call (txnId + abhaNumber)
    after a first verify reported multiple linked accounts.
    """
    txnId: str = Field(min_length=1)
    otp: str = Field(default="", max_length=8)
    abhaNumber: str = Field(default="", max_length=17)


class AbhaMobileSearchRequest(StrictRequest):
    """Find ABHA accounts linked to a mobile number."""
    mobile: str = Field(min_length=10, max_length=10)


class AbhaNumberSearchRequest(StrictRequest):
    """Look up ABHA profile by 14-digit ABHA number."""
    abhaNumber: str = Field(min_length=14, max_length=17)


class PhrSearchRequest(StrictRequest):
    """Search for an ABHA/PHR account by ABHA address."""
    abhaAddress: str = Field(min_length=1, max_length=255)


class PhrOtpRequest(StrictRequest):
    """Send OTP for PHR (ABHA address-based) login."""
    abhaAddress: str = Field(min_length=1, max_length=255)
    txnId: str = Field(default="")
    otpSystem: str = Field(default="abdm")


class PhrVerifyOtpRequest(StrictRequest):
    """Verify OTP for PHR login; returns phrToken."""
    txnId: str = Field(min_length=1)
    otp: str = Field(min_length=4, max_length=8)


class AbhaProfileRequest(StrictRequest):
    """Fetch ABHA profile, card, or QR using the xToken from a verify-otp response."""
    xToken: str = Field(min_length=1)
