from enum import Enum


class DataFlowJobType(str, Enum):
    HIP_HEALTH_INFORMATION_REQUEST = "hipHealthInformationRequest"
    HIU_HEALTH_INFORMATION_REQUEST = "hiuHealthInformationRequest"
    HIU_CONSENT_FETCH = "hiuConsentFetch"


class DataFlowStatus(str, Enum):
    ACCEPTED = "accepted"
    ENCRYPTED_STORED = "encryptedStored"
    DECRYPTED = "decrypted"
    PUSHED = "pushed"
    FAILED = "failed"
    SKIPPED = "skipped"
