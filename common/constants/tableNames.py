from enum import Enum


class TableName(str, Enum):
    HOSPITAL_TENANTS = "sahaiHospitalTenants"
    API_KEYS = "sahaiApiKeys"
    CARE_CONTEXTS = "sahaiCareContexts"
    REQUEST_LOG = "sahaiRequestLog"
    STATUS_STORE = "sahaiStatusStore"
    WEBHOOK_EVENTS = "sahaiWebhookEvents"
    HEALTH_RECORDS = "sahaiHealthRecords"
