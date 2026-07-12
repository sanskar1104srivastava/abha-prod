from __future__ import annotations

import json
from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.abdm.callbackCorrelationService import CallbackCorrelationService
from common.abdm.requestLogService import RequestLogService
from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.eventTypes import EventType
from common.logging.loggingService import LoggingService
from modules.abdmCallbackConsumer.abdmCorrelationDbService import AbdmCorrelationDbService
from modules.callbackRouter.constants import CallbackJobType, CallbackMatchStatus
from modules.callbackRouter.dbService import CallbackRouterDbService
from modules.callbackRouter.responses import CallbackAckResponse


class CallbackRouterApiService:
    def __init__(
        self,
        dbService: CallbackRouterDbService | None = None,
        requestLogService: RequestLogService | None = None,
        correlationService: CallbackCorrelationService | None = None,
        awsService: AwsService | None = None,
        correlationDbService: AbdmCorrelationDbService | None = None,
        abdmClient: AbdmClient | None = None,
    ) -> None:
        self.dbService = dbService or CallbackRouterDbService()
        self.requestLogService = requestLogService or RequestLogService()
        self.correlationService = correlationService or CallbackCorrelationService()
        self.awsService = awsService or AwsService()
        self.correlationDbService = correlationDbService or AbdmCorrelationDbService()
        self.abdmClient = abdmClient or AbdmClient()
        self.settings = getSettings()
        self.logger = LoggingService("callbackRouter")

    def handleCallback(self, path: str, headers: dict[str, Any], payload: dict[str, Any], rawBody: str = "") -> dict[str, Any]:
        self.logger.logInput("handleCallback", headers=headers, body=payload)
        correlationIds = self.correlationService.extractCorrelationIds(path, headers, payload)
        matchedRequest = self.requestLogService.findByCorrelationIds(correlationIds)

        hospitalId = str(matchedRequest.get("hospitalId") or "") if matchedRequest else ""
        if not hospitalId:
            hospitalId = self.correlationDbService.findHospitalId(
                requestId=correlationIds.get("requestId") or "",
                transactionId=correlationIds.get("transactionId") or "",
                consentId=correlationIds.get("consentId") or "",
                consentRequestId=correlationIds.get("consentRequestId") or "",
            ) or ""
        self._enqueueAbdmCallback(path, rawBody or json.dumps(payload), hospitalId)
        self.storeConsentArtefactCorrelations(hospitalId, payload)

        callbackItem = self.dbService.storeRawCallback(path, headers, payload, correlationIds, matchedRequest)
        callbackId = str(callbackItem["callbackId"])
        if matchedRequest:
            self.handleMatchedCallback(path, payload, correlationIds, matchedRequest, callbackId)
            status = CallbackMatchStatus.MATCHED.value
            trackingId = str(matchedRequest.get("trackingId") or "")
        else:
            self.logger.logProcess("unmatchedCallback", callbackId=callbackId, path=path, correlationIds=correlationIds)
            status = CallbackMatchStatus.UNMATCHED.value
            trackingId = None
        ackRequestId = str(correlationIds.get("requestId") or callbackId)
        self.logger.logProcess(
            "callbackAck",
            callbackId=callbackId,
            correlationStatus=status,
            trackingId=trackingId or "",
            responseRequestId=ackRequestId,
        )
        return CallbackAckResponse(
            acknowledgement={"status": "SUCCESS"},
            resp={"requestId": ackRequestId},
        ).model_dump(mode="json")

    async def handleCallbackAsync(self, path: str, headers: dict[str, Any], payload: dict[str, Any], rawBody: str = "") -> dict[str, Any]:
        self.logger.logInput("handleCallback", headers=headers, body=payload)
        correlationIds = self.correlationService.extractCorrelationIds(path, headers, payload)
        matchedRequest = self.requestLogService.findByCorrelationIds(correlationIds)

        hospitalId = str(matchedRequest.get("hospitalId") or "") if matchedRequest else ""
        if not hospitalId:
            hospitalId = self.correlationDbService.findHospitalId(
                requestId=correlationIds.get("requestId") or "",
                transactionId=correlationIds.get("transactionId") or "",
                consentId=correlationIds.get("consentId") or "",
                consentRequestId=correlationIds.get("consentRequestId") or "",
            ) or ""
        self._enqueueAbdmCallback(path, rawBody or json.dumps(payload), hospitalId)
        self.storeConsentArtefactCorrelations(hospitalId, payload)

        callbackItem = self.dbService.storeRawCallback(path, headers, payload, correlationIds, matchedRequest)
        callbackId = str(callbackItem["callbackId"])
        consentAckStatus = await self.ackHipConsentNotifyIfNeeded(path, payload, correlationIds, callbackId)
        if consentAckStatus == "not-applicable":
            consentAckStatus = await self.ackHiuConsentNotifyIfNeeded(path, payload, correlationIds, callbackId)
        if matchedRequest:
            self.handleMatchedCallback(path, payload, correlationIds, matchedRequest, callbackId, consentAckStatus)
            status = CallbackMatchStatus.MATCHED.value
            trackingId = str(matchedRequest.get("trackingId") or "")
        else:
            self.logger.logProcess("unmatchedCallback", callbackId=callbackId, path=path, correlationIds=correlationIds, consentAckStatus=consentAckStatus)
            status = CallbackMatchStatus.UNMATCHED.value
            trackingId = None
        ackRequestId = str(correlationIds.get("requestId") or callbackId)
        self.logger.logProcess(
            "callbackAck",
            callbackId=callbackId,
            correlationStatus=status,
            trackingId=trackingId or "",
            responseRequestId=ackRequestId,
            consentAckStatus=consentAckStatus,
        )
        return CallbackAckResponse(
            acknowledgement={"status": "SUCCESS"},
            resp={"requestId": ackRequestId},
        ).model_dump(mode="json")

    async def ackHipConsentNotifyIfNeeded(
        self,
        path: str,
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        callbackId: str,
    ) -> str:
        if "consent" not in path.lower() or "notify" not in path.lower() or "/hip/" not in path.lower():
            return "not-applicable"
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        consentId = str(notification.get("consentId") or correlationIds.get("consentId") or "").strip()
        requestId = str(payload.get("requestId") or correlationIds.get("requestId") or callbackId).strip()
        if not consentId:
            return "skipped:missing-consent-id"
        ackPayload = {
            "acknowledgement": {
                "status": "OK",
                "consentId": consentId,
            },
            "response": {"requestId": requestId},
        }
        try:
            await self.abdmClient.hipPost("consentHipOnNotify", ackPayload, hipId=correlationIds.get("hipId") or "")
            return "sent"
        except Exception as exc:
            self.logger.logError("consentOnNotifyAckFailed", exc, callbackId=callbackId, consentId=consentId, requestId=requestId)
            return f"failed:{str(exc)[:300]}"

    async def ackHiuConsentNotifyIfNeeded(
        self,
        path: str,
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        callbackId: str,
    ) -> str:
        """Acknowledge a HIU consent notification for every artefact it carries.
        A granted consent can hold multiple artefacts (one per HIP); ABDM expects
        one acknowledgement entry per artefact or it may keep retrying the notify."""
        if "consent" not in path.lower() or "notify" not in path.lower() or "/hiu/" not in path.lower():
            return "not-applicable"
        artefactIds = self.correlationService.extractConsentArtefactIds(payload)
        if not artefactIds:
            return "skipped:no-consent-artefacts"
        requestId = str(payload.get("requestId") or correlationIds.get("requestId") or callbackId).strip()
        ackPayload = {
            "acknowledgement": [{"status": "OK", "consentId": artefactId} for artefactId in artefactIds],
            "response": {"requestId": requestId},
        }
        try:
            await self.abdmClient.hiuPost("consentHiuOnNotify", ackPayload, hiuId=correlationIds.get("hiuId") or "")
            return f"sent:{len(artefactIds)}"
        except Exception as exc:
            self.logger.logError("consentHiuOnNotifyAckFailed", exc, callbackId=callbackId, artefactCount=len(artefactIds), requestId=requestId)
            return f"failed:{str(exc)[:300]}"

    def storeConsentArtefactCorrelations(self, hospitalId: str, payload: dict[str, Any]) -> None:
        """Map every consent artefact ID to the hospital so later callbacks
        (on-fetch, data pushes) referencing any artefact resolve correctly."""
        if not hospitalId:
            return
        artefactIds = self.correlationService.extractConsentArtefactIds(payload)
        if not artefactIds:
            return
        try:
            for artefactId in artefactIds:
                self.correlationDbService.storeCorrelationIds(hospitalId, {"consentId": artefactId})
            self.logger.logProcess("consentArtefactsCorrelated", hospitalId=hospitalId, artefactCount=len(artefactIds))
        except Exception as exc:
            self.logger.logError("consentArtefactCorrelationFailed", exc, hospitalId=hospitalId)

    def _enqueueAbdmCallback(self, path: str, rawBody: str, hospitalId: str) -> None:
        if not self.settings.abdmCallbacksQueueUrl:
            self.logger.logProcess("abdmCallbacksQueueNotConfigured", path=path)
            return
        abdmPath = path.removeprefix("/callback") or path
        self.awsService.sendQueueMessage(
            self.settings.abdmCallbacksQueueUrl,
            {"abdm_path": abdmPath, "raw_body": rawBody, "hospital_id": hospitalId},
        )
        self.logger.logProcess("abdmCallbackEnqueued", path=abdmPath, hospitalId=hospitalId)

    def handleMatchedCallback(
        self,
        path: str,
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        matchedRequest: dict[str, Any],
        callbackId: str,
        consentAckStatus: str = "",
    ) -> None:
        hospitalId = str(matchedRequest["hospitalId"])
        trackingId = str(matchedRequest["trackingId"])
        eventType = self.inferEventType(path, payload)
        self.requestLogService.updateStatus(
            hospitalId,
            trackingId,
            self.inferStatus(payload),
            eventType,
            {"callbackId": callbackId, "path": path, "correlationIds": correlationIds, **({"consentAckStatus": consentAckStatus} if consentAckStatus else {})},
        )
        try:
            self.requestLogService.backfillCorrelation(hospitalId, trackingId, correlationIds)
        except Exception as exc:
            self.logger.logError("backfillCorrelationFailed", exc, hospitalId=hospitalId, trackingId=trackingId)
        self.enqueueWebhookEvent(hospitalId, trackingId, eventType, path, correlationIds, payload, callbackId, matchedRequest)
        if eventType == EventType.CONSENT_GRANTED.value:
            self.enqueueHealthInformationRequestsForConsentArtefacts(
                hospitalId, trackingId, path, correlationIds, payload, matchedRequest, callbackId
            )
        if self.shouldCreateDataFlowJob(path):
            self.enqueueDataFlowJob(hospitalId, trackingId, path, correlationIds, payload, callbackId)

    def enqueueWebhookEvent(
        self,
        hospitalId: str,
        trackingId: str,
        eventType: str,
        path: str,
        correlationIds: dict[str, str],
        payload: dict[str, Any],
        callbackId: str,
        matchedRequest: dict[str, Any],
    ) -> None:
        event = {
            "eventId": AbdmCryptoService.newEventId(),
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "eventType": eventType,
            "callbackId": callbackId,
            "callbackPath": path,
            "correlationIds": {key: value for key, value in correlationIds.items() if value},
            "payload": self.buildThinPayload(path, eventType, payload, matchedRequest),
        }
        self.dbService.storeWebhookEvent(event)
        if self.settings.webhookEventsQueueUrl:
            self.awsService.sendQueueMessage(self.settings.webhookEventsQueueUrl, event)

    def enqueueDataFlowJob(
        self,
        hospitalId: str,
        trackingId: str,
        path: str,
        correlationIds: dict[str, str],
        payload: dict[str, Any],
        callbackId: str,
    ) -> None:
        if not self.settings.dataFlowJobsQueueUrl:
            self.logger.logProcess("dataFlowQueueMissing", callbackId=callbackId, trackingId=trackingId)
            return
        self.awsService.sendQueueMessage(
            self.settings.dataFlowJobsQueueUrl,
            {
                "jobId": AbdmCryptoService.newEventId(),
                "jobType": CallbackJobType.HIP_HEALTH_INFORMATION_REQUEST.value,
                "hospitalId": hospitalId,
                "trackingId": trackingId,
                "callbackId": callbackId,
                "callbackPath": path,
                "correlationIds": {key: value for key, value in correlationIds.items() if value},
                "payload": payload,
            },
        )

    def enqueueHealthInformationRequestsForConsentArtefacts(
        self,
        hospitalId: str,
        trackingId: str,
        path: str,
        correlationIds: dict[str, str],
        payload: dict[str, Any],
        matchedRequest: dict[str, Any],
        callbackId: str,
    ) -> None:
        artefactIds = self.correlationService.extractConsentArtefactIds(payload)
        if not artefactIds:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="no-consent-artefacts")
            return
        if not self.settings.dataFlowJobsQueueUrl:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="data-flow-queue-missing")
            return
        requestPayload = matchedRequest.get("requestPayload") if isinstance(matchedRequest.get("requestPayload"), dict) else {}
        dateRange = requestPayload.get("dateRange") if isinstance(requestPayload.get("dateRange"), dict) else {}
        if not dateRange:
            permission = requestPayload.get("permission") if isinstance(requestPayload.get("permission"), dict) else {}
            dateRange = permission.get("dateRange") if isinstance(permission.get("dateRange"), dict) else {}
        if not dateRange:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="missing-date-range")
            return
        hiuId = str(correlationIds.get("hiuId") or requestPayload.get("hiuId") or matchedRequest.get("hiuId") or "").strip()
        if not hiuId:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="missing-hiu-id")
            return
        hiTypes = requestPayload.get("hiTypes") if isinstance(requestPayload.get("hiTypes"), list) else []
        patientContext = {
            "abhaAddress": str(requestPayload.get("abhaAddress") or ""),
            "patientReference": str(requestPayload.get("patientReference") or ""),
            "consentRequestId": str(matchedRequest.get("consentRequestId") or correlationIds.get("consentRequestId") or ""),
            "consentTrackingId": trackingId,
            "hiTypes": hiTypes,
        }
        for artefactId in artefactIds:
            self.awsService.sendQueueMessage(
                self.settings.dataFlowJobsQueueUrl,
                {
                    "jobId": AbdmCryptoService.newEventId(),
                    "jobType": CallbackJobType.HIU_HEALTH_INFORMATION_REQUEST.value,
                    "hospitalId": hospitalId,
                    "trackingId": trackingId,
                    "callbackId": callbackId,
                    "callbackPath": path,
                    "correlationIds": {
                        **{key: value for key, value in correlationIds.items() if value},
                        "consentId": artefactId,
                        "hiuId": hiuId,
                    },
                    "payload": {
                        "consentId": artefactId,
                        "hiuId": hiuId,
                        "dateRange": dateRange,
                        **patientContext,
                    },
                },
            )
        self.logger.logProcess("healthInformationFanoutQueued", callbackId=callbackId, artefactCount=len(artefactIds))

    @staticmethod
    def shouldCreateDataFlowJob(path: str) -> bool:
        return "health-information/request" in path.lower()

    @staticmethod
    def inferEventType(path: str, payload: dict[str, Any]) -> str:
        loweredPath = path.lower()
        statusText = str(((payload.get("notification") or {}).get("status") if isinstance(payload.get("notification"), dict) else "") or "").upper()
        if "consent" in loweredPath and statusText == "GRANTED":
            return EventType.CONSENT_GRANTED.value
        if "consent" in loweredPath and statusText in {"DENIED", "REVOKED", "EXPIRED"}:
            return EventType.CONSENT_DENIED.value
        if "health-information" in loweredPath and "request" in loweredPath:
            return EventType.HEALTH_INFORMATION_REQUESTED.value
        return EventType.CALLBACK_RECEIVED.value

    @staticmethod
    def inferStatus(payload: dict[str, Any]) -> str:
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        if error:
            return "failed"
        # Consent notifications carry the consent state (GRANTED/DENIED/REVOKED/EXPIRED) —
        # persist it so /v1/status/{trackingId} reflects the real consent state
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        notificationStatus = str(notification.get("status") or "").strip().lower()
        if notificationStatus:
            return notificationStatus
        response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        acknowledgement = response.get("acknowledgement") if isinstance(response.get("acknowledgement"), dict) else {}
        status = str(acknowledgement.get("status") or "").strip().lower()
        return status or "callbackReceived"

    @staticmethod
    def buildThinPayload(path: str, eventType: str, payload: dict[str, Any], matchedRequest: dict[str, Any] | None = None) -> dict[str, Any]:
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        notificationStatus = str(notification.get("status") or "").strip()
        if "consent" in path.lower() and notificationStatus:
            return CallbackRouterApiService.buildConsentStatusPayload(payload, matchedRequest or {}, notificationStatus)
        allowedKeys = {
            "requestId",
            "transactionId",
            "consentRequestId",
            "consentId",
            "response",
            "resp",
            "error",
            "notification",
            "hiRequest",
        }
        return {key: payload[key] for key in allowedKeys if key in payload}

    @staticmethod
    def buildConsentStatusPayload(payload: dict[str, Any], matchedRequest: dict[str, Any], notificationStatus: str) -> dict[str, Any]:
        requestPayload = matchedRequest.get("requestPayload") if isinstance(matchedRequest.get("requestPayload"), dict) else {}
        artefactIds = CallbackCorrelationService.extractConsentArtefactIds(payload)
        artefactSummary: dict[str, Any] = {"count": len(artefactIds)}
        if len(artefactIds) == 1:
            artefactSummary["consentId"] = artefactIds[0]
        summary: dict[str, Any] = {
            "message": f"Consent {notificationStatus.lower()}",
            "status": notificationStatus,
            "requestId": str(matchedRequest.get("requestId") or payload.get("requestId") or ""),
            "consentRequestId": str(matchedRequest.get("consentRequestId") or ""),
            "patient": CallbackRouterApiService.compactDict({
                "abhaAddress": str(requestPayload.get("abhaAddress") or ""),
                "patientReference": str(requestPayload.get("patientReference") or ""),
            }),
            "hiuId": str(matchedRequest.get("hiuId") or requestPayload.get("hiuId") or ""),
            "purpose": requestPayload.get("purpose") if isinstance(requestPayload.get("purpose"), dict) else {},
            "hiTypes": requestPayload.get("hiTypes") if isinstance(requestPayload.get("hiTypes"), list) else [],
            "dateRange": requestPayload.get("dateRange") if isinstance(requestPayload.get("dateRange"), dict) else {},
            "consentArtefacts": artefactSummary,
        }
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        if error:
            summary["error"] = error
        return CallbackRouterApiService.compactDict(summary)

    @staticmethod
    def compactDict(value: dict[str, Any]) -> dict[str, Any]:
        return {key: item for key, item in value.items() if item not in ("", None, [], {})}
