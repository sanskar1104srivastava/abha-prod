from enum import Enum


class EventType(str, Enum):
    PATIENT_REGISTERED = "patient.registered"
    CARE_CONTEXT_REGISTERED = "careContext.registered"
    LINK_TOKEN_REQUESTED = "linkToken.requested"
    CARE_CONTEXT_LINKED = "careContext.linked"
    CONSENT_REQUESTED = "consent.requested"
    CONSENT_GRANTED = "consent.granted"
    CONSENT_DENIED = "consent.denied"
    HEALTH_INFORMATION_REQUESTED = "healthInformation.requested"
    HEALTH_INFORMATION_RECEIVED = "healthInformation.received"
    HEALTH_INFORMATION_PUSHED = "healthInformation.pushed"
    CALLBACK_RECEIVED = "callback.received"
    CALLBACK_UNMATCHED = "callback.unmatched"
    DATA_FLOW_JOB_CREATED = "dataFlow.jobCreated"
    WEBHOOK_DELIVERY_FAILED = "webhook.deliveryFailed"
