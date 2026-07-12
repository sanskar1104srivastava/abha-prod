import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    headers = event.get("headers", {}) or {}
    raw_body = event.get("body", "") or ""

    try:
        body = json.loads(raw_body)
    except Exception:
        body = raw_body

    logger.info("=== WEBHOOK RECEIVED ===")
    logger.info("X-Abdm-Path      : %s", headers.get("x-abdm-path", ""))
    logger.info("X-Abdm-Signature : %s", headers.get("x-abdm-signature", ""))
    logger.info("Headers          : %s", json.dumps(headers, indent=2))
    logger.info("Body             : %s", json.dumps(body, indent=2, default=str))
    logger.info("========================")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"received": True}),
    }
