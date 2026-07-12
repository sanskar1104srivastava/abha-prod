from enum import Enum


class QueueName(str, Enum):
    WEBHOOK_EVENTS = "sahaiWebhookEventsQueue"
    WEBHOOK_EVENTS_DLQ = "sahaiWebhookEventsDlq"
    DATA_FLOW_JOBS = "sahaiDataFlowJobsQueue"
    DATA_FLOW_JOBS_DLQ = "sahaiDataFlowJobsDlq"
