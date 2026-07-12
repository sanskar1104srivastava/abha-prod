from enum import Enum


class LambdaName(str, Enum):
    EXTERNAL_API = "sahai-production-external-api"
    CALLBACK_ROUTER = "sahai-production-callback-router"
    DATA_FLOW = "sahai-production-data-flow"
    WEBHOOK_DISPATCHER = "sahai-production-webhook-dispatcher"
