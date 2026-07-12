from enum import Enum


class IndexName(str, Enum):
    REQUEST_ID_INDEX = "requestIdIndex"
    TRANSACTION_ID_INDEX = "transactionIdIndex"
    CONSENT_REQUEST_ID_INDEX = "consentRequestIdIndex"
    CONSENT_ID_INDEX = "consentIdIndex"
    HIP_ID_INDEX = "hipIdIndex"
    HIU_ID_INDEX = "hiuIdIndex"
    PATIENT_ID_INDEX = "patientIdIndex"
    STATUS_UPDATED_INDEX = "statusUpdatedIndex"
