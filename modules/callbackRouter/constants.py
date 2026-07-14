from enum import Enum


class CallbackRoute(str, Enum):
    ROOT = "/callback"
    PROXY = "/callback/{callbackPath:path}"


class CallbackJobType(str, Enum):
    HIP_HEALTH_INFORMATION_REQUEST = "hipHealthInformationRequest"
    HIU_HEALTH_INFORMATION_REQUEST = "hiuHealthInformationRequest"
    HIU_CONSENT_FETCH = "hiuConsentFetch"


class CallbackMatchStatus(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
