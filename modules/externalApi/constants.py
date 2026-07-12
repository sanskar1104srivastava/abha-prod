from enum import Enum


class ExternalOperation(str, Enum):
    REQUEST_LINK_TOKEN = "external.linkToken.request"
    LINK_CARE_CONTEXT = "external.careContext.link"
    REQUEST_CONSENT = "external.consent.request"
    REQUEST_HEALTH_INFORMATION = "external.healthInformation.request"


class ExternalRoute(str, Enum):
    LINK_TOKEN = "/v1/link-token"
    LINK_CARE_CONTEXTS = "/v1/care-contexts/link"
    CONSENTS = "/v1/consents"
    HEALTH_INFORMATION = "/v1/health-information"
    STATUS = "/v1/status"
    HEALTH_RECORDS = "/v1/health-records"
