from enum import Enum


class WebhookDeliveryStatus(str, Enum):
    DELIVERED = "delivered"
    RETRYABLE_FAILED = "retryableFailed"
    NON_RETRYABLE_FAILED = "nonRetryableFailed"
    CONFIG_MISSING = "configMissing"
