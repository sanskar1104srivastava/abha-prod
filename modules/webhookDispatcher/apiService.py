from __future__ import annotations

import json
from typing import Any

import httpx

from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.constants.eventTypes import EventType
from common.logging.loggingService import LoggingService
from common.security.webhookSignatureService import WebhookSignatureService
from common.utils.jsonUtils import JsonUtils
from common.utils.networkUtils import NetworkUtils
from modules.webhookDispatcher.constants import WebhookDeliveryStatus
from modules.webhookDispatcher.dbService import WebhookDispatcherDbService
from modules.webhookDispatcher.requests import WebhookEventRequest
from modules.webhookDispatcher.responses import WebhookDeliveryResponse


class WebhookDispatcherApiService:
    def __init__(
        self,
        dbService: WebhookDispatcherDbService | None = None,
        signatureService: WebhookSignatureService | None = None,
        awsService: AwsService | None = None,
    ) -> None:
        self.dbService = dbService or WebhookDispatcherDbService()
        self.signatureService = signatureService or WebhookSignatureService()
        self.awsService = awsService or AwsService()
        self.settings = getSettings()
        self.logger = LoggingService("webhookDispatcher")

    async def handleQueueRecords(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        failures: list[dict[str, str]] = []
        for record in records:
            messageId = str(record.get("messageId") or "")
            try:
                event = WebhookEventRequest.model_validate(json.loads(record.get("body") or "{}"))
                result = await self.deliverWebhook(event)
                self.dbService.markDelivery(event.hospitalId, event.eventId, result)
                if bool(result.get("retryable")):
                    failures.append({"itemIdentifier": messageId})
            except Exception as exc:
                self.logger.logError("webhookRecordFailed", exc, messageId=messageId)
                failures.append({"itemIdentifier": messageId})
        return {"batchItemFailures": failures}

    async def deliverWebhook(self, event: WebhookEventRequest) -> dict[str, Any]:
        tenant = self.dbService.getHospitalTenant(event.hospitalId) or {}
        webhookUrl = str(event.webhookUrl or tenant.get("webhookUrl") or "").strip()
        webhookSecret = str(tenant.get("webhookSecret") or "")
        if not webhookUrl or not webhookSecret:
            return WebhookDeliveryResponse(
                eventId=event.eventId,
                status=WebhookDeliveryStatus.CONFIG_MISSING.value,
                retryable=False,
                message=ErrorCode.WEBHOOK_CONFIG_MISSING.value,
            ).model_dump(mode="json")
        try:
            webhookUrl = NetworkUtils.validateExternalHttpsUrl(webhookUrl)
        except Exception as exc:
            return WebhookDeliveryResponse(
                eventId=event.eventId,
                status=WebhookDeliveryStatus.NON_RETRYABLE_FAILED.value,
                retryable=False,
                message=str(exc),
            ).model_dump(mode="json")
        body = self.buildWebhookBody(event)
        encryptedS3Key = str(event.payload.get("encryptedS3Key") or "")
        if encryptedS3Key and event.eventType == EventType.HEALTH_INFORMATION_RECEIVED.value:
            try:
                s3Object = self.awsService.getJsonObject(self.settings.encryptedRecordsBucket, encryptedS3Key)
                pushPayload = s3Object.get("payload") if isinstance(s3Object.get("payload"), dict) else {}
                body["encryptedData"] = pushPayload.get("entries") or []
                # keyMaterial + transactionId make this body directly usable with
                # POST /v1/health-information/decrypt — no separate lookup needed
                body["keyMaterial"] = pushPayload.get("keyMaterial") or {}
                body["transactionId"] = str(pushPayload.get("transactionId") or "")
            except Exception as exc:
                self.logger.logError("encryptedDataReadFailed", exc, eventId=event.eventId, s3Key=encryptedS3Key)
        bodyText = JsonUtils.dumps(body)
        headers = {
            "Content-Type": "application/json",
            "X-Sahai-Event-Id": event.eventId,
            "X-Sahai-Event-Type": event.eventType,
            "X-Sahai-Signature": self.signatureService.signPayload(webhookSecret, bodyText),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(webhookUrl, content=bodyText, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            return WebhookDeliveryResponse(
                eventId=event.eventId,
                status=WebhookDeliveryStatus.RETRYABLE_FAILED.value,
                retryable=True,
                message=str(exc),
            ).model_dump(mode="json")
        if response.status_code >= 500:
            return WebhookDeliveryResponse(
                eventId=event.eventId,
                status=WebhookDeliveryStatus.RETRYABLE_FAILED.value,
                statusCode=response.status_code,
                retryable=True,
                message=response.text[:500],
            ).model_dump(mode="json")
        if response.status_code >= 400:
            return WebhookDeliveryResponse(
                eventId=event.eventId,
                status=WebhookDeliveryStatus.NON_RETRYABLE_FAILED.value,
                statusCode=response.status_code,
                retryable=False,
                message=response.text[:500],
            ).model_dump(mode="json")
        if encryptedS3Key:
            try:
                self.awsService.deleteObject(self.settings.encryptedRecordsBucket, encryptedS3Key)
            except Exception as exc:
                self.logger.logError("encryptedDataDeleteFailed", exc, eventId=event.eventId, s3Key=encryptedS3Key)
        return WebhookDeliveryResponse(
            eventId=event.eventId,
            status=WebhookDeliveryStatus.DELIVERED.value,
            statusCode=response.status_code,
            retryable=False,
            message="delivered",
        ).model_dump(mode="json")

    @staticmethod
    def buildWebhookBody(event: WebhookEventRequest) -> dict[str, Any]:
        return {
            "eventId": event.eventId,
            "eventType": event.eventType,
            "trackingId": event.trackingId,
            "callbackId": event.callbackId,
            "callbackPath": event.callbackPath,
            "correlationIds": event.correlationIds,
            "payload": event.payload,
        }
