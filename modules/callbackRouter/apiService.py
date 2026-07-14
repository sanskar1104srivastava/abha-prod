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
    CONSENT_FETCH_INITIAL_DELAY_SECONDS = 10
    CONSENT_FETCH_STEP_DELAY_SECONDS = 1
    CONSENT_FETCH_MAX_DELAY_SECONDS = 900
    CONSENT_FETCH_MAX_RETRIES = 2
    CONSENT_FETCH_RETRY_DELAYS_SECONDS = (30, 120)

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
        ackRequestId = self.resolveCallbackRequestId(headers, payload, correlationIds, callbackId)
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
        consentAckStatus = await self.ackHipConsentNotifyIfNeeded(path, headers, payload, correlationIds, callbackId)
        if consentAckStatus == "not-applicable":
            consentAckStatus = await self.ackHiuConsentNotifyIfNeeded(path, headers, payload, correlationIds, callbackId)
        if matchedRequest:
            self.handleMatchedCallback(path, payload, correlationIds, matchedRequest, callbackId, consentAckStatus)
            status = CallbackMatchStatus.MATCHED.value
            trackingId = str(matchedRequest.get("trackingId") or "")
        else:
            self.logger.logProcess("unmatchedCallback", callbackId=callbackId, path=path, correlationIds=correlationIds, consentAckStatus=consentAckStatus)
            status = CallbackMatchStatus.UNMATCHED.value
            trackingId = None
        ackRequestId = self.resolveCallbackRequestId(headers, payload, correlationIds, callbackId)
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
        headers: dict[str, Any],
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        callbackId: str,
    ) -> str:
        if "consent" not in path.lower() or "notify" not in path.lower() or "/hip/" not in path.lower():
            return "not-applicable"
        notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
        consentId = str(notification.get("consentId") or correlationIds.get("consentId") or "").strip()
        requestId = self.resolveCallbackRequestId(headers, payload, correlationIds, callbackId)
        if not consentId:
            return "skipped:missing-consent-id"
        ackRequestId = AbdmCryptoService.newRequestId()
        ackPayload = {
            "acknowledgement": {
                "status": "OK",
                "consentId": consentId,
            },
            "response": {"requestId": requestId},
        }
        try:
            await self.abdmClient.hipPost(
                "consentHipOnNotify",
                ackPayload,
                extraHeaders={"REQUEST-ID": ackRequestId},
                hipId=correlationIds.get("hipId") or "",
            )
            return "sent"
        except Exception as exc:
            self.logger.logError("consentOnNotifyAckFailed", exc, callbackId=callbackId, consentId=consentId, requestId=requestId, ackRequestId=ackRequestId, upstream=getattr(exc, "details", None))
            return f"failed:{str(exc)[:300]}"

    async def ackHiuConsentNotifyIfNeeded(
        self,
        path: str,
        headers: dict[str, Any],
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
        requestId = self.resolveCallbackRequestId(headers, payload, correlationIds, callbackId)
        ackRequestId = AbdmCryptoService.newRequestId()
        ackPayload = {
            "acknowledgement": [{"status": "OK", "consentId": artefactId} for artefactId in artefactIds],
            "response": {"requestId": requestId},
        }
        try:
            await self.abdmClient.hiuPost(
                "consentHiuOnNotify",
                ackPayload,
                extraHeaders={"REQUEST-ID": ackRequestId},
                hiuId=correlationIds.get("hiuId") or "",
            )
            return f"sent:{len(artefactIds)}"
        except Exception as exc:
            self.logger.logError("consentHiuOnNotifyAckFailed", exc, callbackId=callbackId, artefactCount=len(artefactIds), requestId=requestId, ackRequestId=ackRequestId, upstream=getattr(exc, "details", None))
            return f"failed:{str(exc)[:300]}"

    @staticmethod
    def resolveCallbackRequestId(
        headers: dict[str, Any],
        payload: dict[str, Any],
        correlationIds: dict[str, str],
        callbackId: str,
    ) -> str:
        loweredHeaders = {str(key).lower().replace("_", "-"): str(value) for key, value in headers.items()}
        return str(
            payload.get("requestId")
            or loweredHeaders.get("request-id")
            or correlationIds.get("requestId")
            or callbackId
        ).strip()

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
        consentFetchRetryStatus = self.retryConsentFetchIfTransientArtefactError(hospitalId, trackingId, path, payload, callbackId)
        if consentFetchRetryStatus == "queued":
            self.logger.logProcess(
                "parentStatusUpdateSkipped",
                callbackId=callbackId,
                trackingId=trackingId,
                reason="consent-fetch-retry-queued",
            )
        else:
            self.requestLogService.updateStatus(
                hospitalId,
                trackingId,
                self.inferStatus(payload),
                eventType,
                {"callbackId": callbackId, "path": path, "correlationIds": correlationIds, **({"consentAckStatus": consentAckStatus} if consentAckStatus else {})},
            )
        try:
            self.requestLogService.backfillCorrelation(hospitalId, trackingId, correlationIds)
            correlationUpdates = {
                key: value
                for key, value in correlationIds.items()
                if key in {"consentRequestId", "transactionId", "consentId"} and value
            }
            if correlationUpdates:
                matchedRequest = {**matchedRequest, **correlationUpdates}
        except Exception as exc:
            self.logger.logError("backfillCorrelationFailed", exc, hospitalId=hospitalId, trackingId=trackingId)
        if consentFetchRetryStatus == "queued":
            self.logger.logProcess(
                "webhookEventSkipped",
                callbackId=callbackId,
                trackingId=trackingId,
                reason="transient-consent-fetch-error",
            )
        else:
            self.enqueueWebhookEvent(hospitalId, trackingId, eventType, path, correlationIds, payload, callbackId, matchedRequest)
        if eventType == EventType.CONSENT_GRANTED.value:
            self.indexConsentArtefactsForRequest(hospitalId, trackingId, correlationIds, payload)
            self.enqueueConsentFetchRequestsForConsentArtefacts(
                hospitalId, trackingId, path, correlationIds, payload, matchedRequest, callbackId
            )
        if self.shouldCreateHealthInformationRequestFromConsentFetch(path, payload):
            self.enqueueHealthInformationRequestForFetchedConsent(
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

    def indexConsentArtefactsForRequest(
        self,
        hospitalId: str,
        trackingId: str,
        correlationIds: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        artefactIds = self.correlationService.extractConsentArtefactIds(payload)
        consentRequestId = str(correlationIds.get("consentRequestId") or "").strip()
        for artefactId in artefactIds:
            self.requestLogService.recordConsentArtefactIndex(hospitalId, trackingId, consentRequestId, artefactId)

    def enqueueConsentFetchRequestsForConsentArtefacts(
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
            self.logger.logProcess("consentFetchFanoutSkipped", callbackId=callbackId, reason="no-consent-artefacts")
            return
        if not self.settings.dataFlowJobsQueueUrl:
            self.logger.logProcess("consentFetchFanoutSkipped", callbackId=callbackId, reason="data-flow-queue-missing")
            return
        requestPayload = matchedRequest.get("requestPayload") if isinstance(matchedRequest.get("requestPayload"), dict) else {}
        hiuId = str(correlationIds.get("hiuId") or requestPayload.get("hiuId") or matchedRequest.get("hiuId") or "").strip()
        if not hiuId:
            self.logger.logProcess("consentFetchFanoutSkipped", callbackId=callbackId, reason="missing-hiu-id")
            return
        maxDelaySeconds = 0
        for index, artefactId in enumerate(artefactIds):
            delaySeconds = self.consentFetchDelaySeconds(index)
            maxDelaySeconds = max(maxDelaySeconds, delaySeconds)
            self.awsService.sendQueueMessage(
                self.settings.dataFlowJobsQueueUrl,
                {
                    "jobId": AbdmCryptoService.newEventId(),
                    "jobType": CallbackJobType.HIU_CONSENT_FETCH.value,
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
                        "consentRequestId": str(matchedRequest.get("consentRequestId") or correlationIds.get("consentRequestId") or ""),
                        "consentTrackingId": trackingId,
                        "consentFetchAttempt": 0,
                        "consentFetchIndex": index,
                    },
                },
                delaySeconds=delaySeconds,
            )
        self.logger.logProcess(
            "consentFetchFanoutQueued",
            callbackId=callbackId,
            artefactCount=len(artefactIds),
            maxDelaySeconds=maxDelaySeconds,
        )

    def retryConsentFetchIfTransientArtefactError(
        self,
        hospitalId: str,
        trackingId: str,
        path: str,
        payload: dict[str, Any],
        callbackId: str,
    ) -> str:
        if not self.isTransientConsentFetchArtefactError(path, payload):
            return "not-applicable"
        if not self.settings.dataFlowJobsQueueUrl:
            self.logger.logProcess("consentFetchRetrySkipped", callbackId=callbackId, reason="data-flow-queue-missing")
            return "skipped"
        response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        requestId = str(response.get("requestId") or payload.get("requestId") or "").strip()
        if not requestId:
            self.logger.logProcess("consentFetchRetrySkipped", callbackId=callbackId, reason="missing-response-request-id")
            return "skipped"
        fetchRow = self.requestLogService.findConsentFetchByRequestId(requestId)
        if not fetchRow:
            self.logger.logProcess("consentFetchRetrySkipped", callbackId=callbackId, reason="fetch-row-not-found", requestId=requestId)
            return "skipped"
        requestPayload = fetchRow.get("requestPayload") if isinstance(fetchRow.get("requestPayload"), dict) else {}
        attempt = self.safeInt(requestPayload.get("consentFetchAttempt"), 0)
        if attempt >= self.CONSENT_FETCH_MAX_RETRIES:
            self.logger.logProcess(
                "consentFetchRetryExhausted",
                callbackId=callbackId,
                requestId=requestId,
                attempt=attempt,
            )
            return "exhausted"
        consentId = str(fetchRow.get("consentId") or requestPayload.get("consentId") or "").strip()
        hiuId = str(requestPayload.get("hiuId") or fetchRow.get("hiuId") or "").strip()
        if not consentId or not hiuId:
            self.logger.logProcess("consentFetchRetrySkipped", callbackId=callbackId, reason="missing-consent-or-hiu-id")
            return "skipped"
        nextAttempt = attempt + 1
        delaySeconds = self.consentFetchRetryDelaySeconds(nextAttempt)
        fetchTrackingId = str(fetchRow.get("trackingId") or trackingId)
        fetchHospitalId = str(fetchRow.get("hospitalId") or hospitalId)
        consentRequestId = str(fetchRow.get("consentRequestId") or requestPayload.get("consentRequestId") or "")
        self.awsService.sendQueueMessage(
            self.settings.dataFlowJobsQueueUrl,
            {
                "jobId": AbdmCryptoService.newEventId(),
                "jobType": CallbackJobType.HIU_CONSENT_FETCH.value,
                "hospitalId": fetchHospitalId,
                "trackingId": fetchTrackingId,
                "callbackId": callbackId,
                "callbackPath": path,
                "correlationIds": {
                    "requestId": requestId,
                    "consentId": consentId,
                    "consentRequestId": consentRequestId,
                    "hiuId": hiuId,
                },
                "payload": {
                    **requestPayload,
                    "consentId": consentId,
                    "hiuId": hiuId,
                    "consentRequestId": consentRequestId,
                    "consentTrackingId": str(requestPayload.get("consentTrackingId") or fetchTrackingId),
                    "consentFetchAttempt": nextAttempt,
                    "consentFetchRetryForRequestId": requestId,
                },
            },
            delaySeconds=delaySeconds,
        )
        self.logger.logProcess(
            "consentFetchRetryQueued",
            callbackId=callbackId,
            consentId=consentId,
            attempt=nextAttempt,
            delaySeconds=delaySeconds,
        )
        return "queued"

    def enqueueHealthInformationRequestForFetchedConsent(
        self,
        hospitalId: str,
        trackingId: str,
        path: str,
        correlationIds: dict[str, str],
        payload: dict[str, Any],
        matchedRequest: dict[str, Any],
        callbackId: str,
    ) -> None:
        if not self.settings.dataFlowJobsQueueUrl:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="data-flow-queue-missing")
            return
        consent = payload.get("consent") if isinstance(payload.get("consent"), dict) else {}
        if str(consent.get("status") or "").strip().upper() != "GRANTED":
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="consent-not-granted")
            return
        detail = consent.get("consentDetail") if isinstance(consent.get("consentDetail"), dict) else {}
        consentId = str(detail.get("consentId") or correlationIds.get("consentId") or "").strip()
        requestPayload = matchedRequest.get("requestPayload") if isinstance(matchedRequest.get("requestPayload"), dict) else {}
        hiu = detail.get("hiu") if isinstance(detail.get("hiu"), dict) else {}
        hiuId = str(hiu.get("id") or correlationIds.get("hiuId") or requestPayload.get("hiuId") or matchedRequest.get("hiuId") or "").strip()
        permission = detail.get("permission") if isinstance(detail.get("permission"), dict) else {}
        dateRange = permission.get("dateRange") if isinstance(permission.get("dateRange"), dict) else {}
        if not dateRange:
            dateRange = requestPayload.get("dateRange") if isinstance(requestPayload.get("dateRange"), dict) else {}
        if not dateRange:
            originalPermission = requestPayload.get("permission") if isinstance(requestPayload.get("permission"), dict) else {}
            dateRange = originalPermission.get("dateRange") if isinstance(originalPermission.get("dateRange"), dict) else {}
        if not consentId or not hiuId or not dateRange:
            self.logger.logProcess("healthInformationFanoutSkipped", callbackId=callbackId, reason="missing-consent-hiu-or-date-range")
            return
        patient = detail.get("patient") if isinstance(detail.get("patient"), dict) else {}
        hiTypes = detail.get("hiTypes") if isinstance(detail.get("hiTypes"), list) else []
        if not hiTypes:
            hiTypes = requestPayload.get("hiTypes") if isinstance(requestPayload.get("hiTypes"), list) else []
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
                    "consentId": consentId,
                    "hiuId": hiuId,
                },
                "payload": {
                    "consentId": consentId,
                    "hiuId": hiuId,
                    "dateRange": dateRange,
                    "abhaAddress": str(requestPayload.get("abhaAddress") or patient.get("id") or ""),
                    "patientReference": str(requestPayload.get("patientReference") or ""),
                    "consentRequestId": str(matchedRequest.get("consentRequestId") or correlationIds.get("consentRequestId") or ""),
                    "consentTrackingId": trackingId,
                    "hiTypes": hiTypes,
                },
            },
        )
        self.logger.logProcess("healthInformationFanoutQueued", callbackId=callbackId, consentId=consentId)

    @staticmethod
    def shouldCreateDataFlowJob(path: str) -> bool:
        return "health-information/request" in path.lower()

    @staticmethod
    def shouldCreateHealthInformationRequestFromConsentFetch(path: str, payload: dict[str, Any]) -> bool:
        return "consent" in path.lower() and "on-fetch" in path.lower() and isinstance(payload.get("consent"), dict)

    @classmethod
    def consentFetchDelaySeconds(cls, index: int) -> int:
        delay = cls.CONSENT_FETCH_INITIAL_DELAY_SECONDS + max(int(index or 0), 0) * cls.CONSENT_FETCH_STEP_DELAY_SECONDS
        return min(max(delay, 0), cls.CONSENT_FETCH_MAX_DELAY_SECONDS)

    @classmethod
    def consentFetchRetryDelaySeconds(cls, attempt: int) -> int:
        if attempt <= 0:
            return cls.CONSENT_FETCH_RETRY_DELAYS_SECONDS[0]
        index = min(attempt - 1, len(cls.CONSENT_FETCH_RETRY_DELAYS_SECONDS) - 1)
        return min(max(cls.CONSENT_FETCH_RETRY_DELAYS_SECONDS[index], 0), cls.CONSENT_FETCH_MAX_DELAY_SECONDS)

    @staticmethod
    def isTransientConsentFetchArtefactError(path: str, payload: dict[str, Any]) -> bool:
        loweredPath = path.lower()
        if "consent" not in loweredPath or "on-fetch" not in loweredPath:
            return False
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        if not error:
            return False
        code = str(error.get("code") or error.get("errorCode") or "").strip().upper()
        message = str(error.get("message") or error.get("errorMessage") or "").strip().lower()
        return "ABDM-1080" in code or "invalid consent artefact" in message or "invalid consent artifact" in message

    @staticmethod
    def safeInt(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

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
        consent = payload.get("consent") if isinstance(payload.get("consent"), dict) else {}
        consentStatus = str(consent.get("status") or "").strip().lower()
        if consentStatus:
            return consentStatus
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
