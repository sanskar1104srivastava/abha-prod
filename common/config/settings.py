from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    appName: str = "sahai-production-backend"
    appEnv: str = "production"
    awsProfile: str = "algoflow"
    awsRegion: str = "ap-south-1"
    configSecretName: str = ""

    encryptedRecordsBucket: str = "sahai-production-encrypted-records"
    decryptedRecordsBucket: str = "sahai-production-decrypted-records"
    callbackBodyBucket: str = "sahai-production-callback-bodies"

    webhookEventsQueueUrl: str = ""
    dataFlowJobsQueueUrl: str = ""
    abdmCallbacksQueueUrl: str = ""

    abdmGatewayBase: str = ""
    abdmAbhaBase: str = ""
    abdmAbhaCertUrl: str = ""
    abdmAbhaPublicKey: str = ""
    abdmAbhaRegistrationV1Base: str = ""
    abdmCmId: str = ""
    abdmClientId: str = ""
    abdmClientSecret: str = ""
    abdmGatewayToken: str = ""
    abdmHipId: str = ""
    abdmHiuId: str = ""
    abdmEndpoints: dict[str, str] = Field(default_factory=dict)
    facilityBridgeUrl: str = ""
    selfCallbackUrl: str = ""
    adminKey: str = ""
    requestTtlDays: int = 30
    selfDataEndpointUrl: str = ""

    def abdmEndpoint(self, endpointKey: str) -> str:
        value = str(self.abdmEndpoints.get(endpointKey) or "").strip()
        if not value:
            raise RuntimeError(f"ABDM endpoint key is not configured in Secrets Manager: {endpointKey}")
        return value


@lru_cache(maxsize=1)
def getSettings() -> Settings:
    baseSettings = Settings()
    secretValues = loadSecretValues(baseSettings)
    if not secretValues:
        return baseSettings
    return baseSettings.model_copy(update=secretValues)


def loadSecretValues(baseSettings: Settings) -> dict[str, Any]:
    if not baseSettings.configSecretName:
        return {}
    from common.aws.awsService import AwsService

    secretText = AwsService(
        awsRegion=baseSettings.awsRegion,
        awsProfile=baseSettings.awsProfile,
    ).getSecretString(baseSettings.configSecretName)
    if not secretText:
        return {}
    parsed = json.loads(secretText)
    if not isinstance(parsed, dict):
        raise RuntimeError("Secrets Manager config payload must be a JSON object")
    return parsed
