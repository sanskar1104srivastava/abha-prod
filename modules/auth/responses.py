from __future__ import annotations

from pydantic import BaseModel


class AuthTokenResponse(BaseModel):
    hospitalId: str
    loginId: str
    hospitalName: str
    apiKey: str
    environment: str
    message: str


class LoginResponse(BaseModel):
    hospitalId: str
    loginId: str
    hospitalName: str
    environment: str
    message: str


class HospitalProfileResponse(BaseModel):
    hospitalId: str
    loginId: str
    hospitalName: str
    environment: str
    hipId: str
    hiuId: str
    webhookUrl: str | None
    dataPushUrl: str | None = None
    createdAt: str
    updatedAt: str | None = None
