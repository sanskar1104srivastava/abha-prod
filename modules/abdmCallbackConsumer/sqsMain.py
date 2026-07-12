from __future__ import annotations

import asyncio
import json
from typing import Any

from common.logging.loggingService import LoggingService
from modules.abdmCallbackConsumer.correlationService import AbdmCallbackCorrelationService
from modules.abdmCallbackConsumer.forwarderService import AbdmCallbackForwarderService

logger = LoggingService("abdmCallbackConsumer")
correlationSvc = AbdmCallbackCorrelationService()
forwarderSvc = AbdmCallbackForwarderService()


async def _processRecord(record: dict[str, Any]) -> bool:
    messageId = str(record.get("messageId") or "")
    try:
        message = json.loads(record.get("body") or "{}")
        abdmPath = str(message.get("abdm_path") or "")
        rawBody = str(message.get("raw_body") or "{}")
        hospitalIdHint = str(message.get("hospital_id") or "")

        try:
            payload = json.loads(rawBody)
        except Exception:
            payload = {}

        hospitalId = correlationSvc.resolveHospitalId(abdmPath, payload, hospitalIdHint)
        if not hospitalId:
            logger.logProcess("unroutableCallback", messageId=messageId, path=abdmPath)
            return True  # discard, do not retry

        success, retryable = await forwarderSvc.forward(hospitalId, abdmPath, rawBody)
        if not success and retryable:
            return False
        return True
    except Exception as exc:
        logger.logError("recordFailed", exc, messageId=messageId)
        return False


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    async def run() -> list[dict[str, str]]:
        failures: list[dict[str, str]] = []
        for record in event.get("Records") or []:
            ok = await _processRecord(record)
            if not ok:
                failures.append({"itemIdentifier": str(record.get("messageId") or "")})
        return failures

    return {"batchItemFailures": asyncio.run(run())}
