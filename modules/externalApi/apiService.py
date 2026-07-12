from __future__ import annotations

from typing import Any

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.abdm.requestLogService import RequestLogService
from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.constants.eventTypes import EventType
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.security.idempotencyService import IdempotencyService
from common.utils.dateTimeUtils import DateTimeUtils
from common.utils.hashUtils import HashUtils
from common.utils.jsonUtils import JsonUtils
from modules.abdmCallbackConsumer.abdmCorrelationDbService import AbdmCorrelationDbService
from modules.externalApi.constants import ExternalOperation
from modules.externalApi.dbService import ExternalApiDbService
from modules.externalApi.requests import (
    CareContextLinkRequest,
    ConsentFetchRequest,
    ConsentRequest,
    ConsentStatusRequest,
    HealthInformationDecryptRequest,
    HealthInformationRequest,
    LinkTokenRequest,
)
from modules.externalApi.responses import AcceptedResponse, ResultResponse, StatusResponse


class ExternalApiService:
    def __init__(
        self,
        dbService: ExternalApiDbService | None = None,
        idempotencyService: IdempotencyService | None = None,
        requestLogService: RequestLogService | None = None,
        abdmClient: AbdmClient | None = None,
        awsService: AwsService | None = None,
        correlationDbService: AbdmCorrelationDbService | None = None,
    ) -> None:
        self.dbService = dbService or ExternalApiDbService()
        self.idempotencyService = idempotencyService or IdempotencyService()
        self.requestLogService = requestLogService or RequestLogService()
        self.abdmClient = abdmClient or AbdmClient()
        self.awsService = awsService or AwsService()
        self.correlationDbService = correlationDbService or AbdmCorrelationDbService()
        self.settings = getSettings()
        self.logger = LoggingService("externalApi")

    # ── sync flows (no ABDM call) ────────────────────────────────────────────

    def getStatus(self, hospitalId: str, trackingId: str) -> dict[str, Any]:
        item = self.requestLogService.getStatus(hospitalId, trackingId)
        if not item:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "Tracking ID was not found for this hospital")
        return StatusResponse(
            trackingId=trackingId,
            status=str(item.get("status") or "unknown"),
            eventType=item.get("eventType"),
            details=item.get("details") if isinstance(item.get("details"), dict) else {},
        ).model_dump(mode="json")

    def getHealthRecordResult(self, hospitalId: str, trackingId: str) -> dict[str, Any]:
        records = self.dbService.getDecryptedRecordsByTrackingId(hospitalId, trackingId)
        inboundPush = self.dbService.getInboundDataPushByTrackingId(hospitalId, trackingId)
        statusItem = self.requestLogService.getStatus(hospitalId, trackingId)
        if not records and not inboundPush:
            if not statusItem:
                raise AppError(404, ErrorCode.INVALID_REQUEST, "Tracking ID was not found for this hospital")
            status = str(statusItem.get("status") or "pending")
            if status in {"accepted", "dispatched"}:
                status = "pending"
            return ResultResponse(
                trackingId=trackingId,
                status=status,
                result={"details": statusItem.get("details") if isinstance(statusItem.get("details"), dict) else {}},
            ).model_dump(mode="json")
        statusDetails = statusItem.get("details") if statusItem and isinstance(statusItem.get("details"), dict) else {}
        result: dict[str, Any] = {
            "decryptedCount": len(records),
            "records": [
                {
                    "recordId": str(record.get("recordId") or ""),
                    "careContextReference": str(record.get("careContextReference") or ""),
                    "media": str(record.get("media") or ""),
                    "transactionId": str(record.get("transactionId") or ""),
                    "createdAt": str(record.get("createdAt") or ""),
                }
                for record in records
            ],
            "details": statusDetails,
        }
        if inboundPush:
            result["receivedAt"] = str(inboundPush.get("receivedAt") or "")
            result["entryCount"] = int(inboundPush.get("entryCount") or 0)
            result["transactionId"] = str(inboundPush.get("transactionId") or "")
        status = "decrypted" if records else str((inboundPush or {}).get("status") or "received")
        return ResultResponse(trackingId=trackingId, status=status, result=result).model_dump(mode="json")

    def getDecryptedRecords(self, hospitalId: str, trackingId: str, apiKeyHash: str = "") -> dict[str, Any]:
        records = self.dbService.getDecryptedRecordsByTrackingId(hospitalId, trackingId)
        if not records:
            statusItem = self.requestLogService.getStatus(hospitalId, trackingId)
            if not statusItem:
                raise AppError(404, ErrorCode.INVALID_REQUEST, "Tracking ID was not found for this hospital")
            details = statusItem.get("details") if isinstance(statusItem.get("details"), dict) else {}
            decryptErrors = details.get("errors") if isinstance(details.get("errors"), list) else []
            if decryptErrors:
                raise AppError(
                    424,
                    ErrorCode.DATA_DECRYPTION_FAILED,
                    "Health data arrived but could not be decrypted",
                    {"trackingId": trackingId, "errors": decryptErrors},
                )
            raise AppError(
                404,
                ErrorCode.INVALID_REQUEST,
                "No decrypted records yet for this tracking ID — the HIP has not pushed data. Poll GET /v1/status/{trackingId}.",
            )
        entries = []
        readErrorCount = 0
        for record in records:
            s3Key = str(record.get("decryptedS3Key") or "")
            entry: dict[str, Any] = {
                "careContextReference": str(record.get("careContextReference") or ""),
                "media": str(record.get("media") or "application/fhir+json"),
            }
            try:
                entry["fhir"] = self.awsService.getJsonObject(self.settings.decryptedRecordsBucket, s3Key)
            except Exception as exc:
                entry["fhir"] = {}
                entry["error"] = f"Stored record could not be read: {exc}"
                readErrorCount += 1
            entries.append(entry)
        self.dbService.recordAccessAudit(hospitalId, "decryptedRecordsFetched", {
            "trackingId": trackingId,
            "entryCount": len(entries),
            "readErrorCount": readErrorCount,
            "apiKeyHash": apiKeyHash,
        })
        return {
            "trackingId": trackingId,
            "status": "decrypted",
            "entryCount": len(entries),
            "readErrorCount": readErrorCount,
            "entries": entries,
        }

    # ── async flows (call ABDM after accepting) ──────────────────────────────

    async def requestLinkToken(self, hospitalId: str, idempotencyKey: str, requestBody: LinkTokenRequest) -> dict[str, Any]:
        payload = requestBody.model_dump(mode="json")
        requestId = AbdmCryptoService.newRequestId()
        hipId = str(payload.get("hipId") or "")
        correlation: dict[str, str] = {"requestId": requestId}
        if hipId:
            correlation["hipId"] = hipId
        response, trackingId, isReplay = self._acceptAndLog(
            hospitalId, idempotencyKey, ExternalOperation.REQUEST_LINK_TOKEN.value, EventType.LINK_TOKEN_REQUESTED.value, payload, correlation
        )
        if not isReplay:
            await self._dispatchLinkToken(hospitalId, trackingId, payload, requestId)
        return response

    async def linkCareContexts(self, hospitalId: str, idempotencyKey: str, requestBody: CareContextLinkRequest) -> dict[str, Any]:
        payload = requestBody.model_dump(mode="json")
        logPayload = self.compactCareContextLinkPayload(payload)
        hipId = str(payload.get("hipId") or "")
        requestId = AbdmCryptoService.newRequestId()
        correlation: dict[str, str] = {"requestId": requestId}
        if hipId:
            correlation["hipId"] = hipId
        response, trackingId, isReplay = self._acceptAndLog(
            hospitalId, idempotencyKey, ExternalOperation.LINK_CARE_CONTEXT.value, EventType.CARE_CONTEXT_LINKED.value, logPayload, correlation
        )
        if not isReplay:
            await self._dispatchLinkCareContexts(hospitalId, trackingId, payload, requestId)
        return response

    async def requestConsent(self, hospitalId: str, hiuId: str, idempotencyKey: str, requestBody: ConsentRequest) -> dict[str, Any]:
        payload = requestBody.model_dump(mode="json")
        requestId = AbdmCryptoService.newRequestId()
        correlation = {"requestId": requestId, "consentRequestId": requestId, "hiuId": hiuId}
        response, trackingId, isReplay = self._acceptAndLog(
            hospitalId, idempotencyKey, ExternalOperation.REQUEST_CONSENT.value, EventType.CONSENT_REQUESTED.value, payload, correlation
        )
        response["consentRequestId"] = str(response.get("consentRequestId") or response.get("requestId") or requestId)
        if not isReplay:
            await self._dispatchConsentInit(hospitalId, trackingId, requestId, payload, hiuId)
        return response

    async def requestHealthInformation(self, hospitalId: str, hiuId: str, idempotencyKey: str, requestBody: HealthInformationRequest) -> dict[str, Any]:
        idempotencyPayload = requestBody.model_dump(mode="json")
        for key in ("abhaAddress", "patientReference", "consentRequestId", "consentTrackingId", "hiTypes"):
            if not idempotencyPayload.get(key):
                idempotencyPayload.pop(key, None)
        payload = dict(idempotencyPayload)
        privateKeyB64, publicKeyB64, nonceB64 = AbdmCryptoService.generateFideliusEcdhKeypair()
        transactionId = payload.get("transactionId") or AbdmCryptoService.newRequestId()
        correlation = {"consentId": payload["consentId"], "transactionId": transactionId}
        payload["transactionId"] = transactionId
        # 24h expiry — HIPs often push well after an hour; an expired key makes them refuse the request
        payload["keyMaterial"] = AbdmCryptoService.keyMaterial(publicKeyB64, nonceB64, DateTimeUtils.utcIsoAfter(hours=24))
        payload["keySession"] = {"privateKey": privateKeyB64, "nonce": nonceB64}
        response, trackingId, isReplay = self._acceptAndLog(
            hospitalId,
            idempotencyKey,
            ExternalOperation.REQUEST_HEALTH_INFORMATION.value,
            EventType.HEALTH_INFORMATION_REQUESTED.value,
            payload,
            correlation,
            idempotencyPayload=idempotencyPayload,
        )
        if not isReplay:
            await self._dispatchHealthInfoRequest(hospitalId, trackingId, payload, hiuId)
        return response

    # ── ABDM dispatch helpers ────────────────────────────────────────────────

    async def _dispatchLinkToken(self, hospitalId: str, trackingId: str, payload: dict[str, Any], requestId: str = "") -> None:
        try:
            hipId = str(payload.get("hipId") or "")
            abhaNumber = str(payload.get("abhaNumber") or "").replace("-", "")
            abdmPayload: dict[str, Any] = {
                "abhaAddress": str(payload.get("abhaAddress") or ""),
                "name": str(payload.get("name") or ""),
                "gender": str(payload.get("gender") or ""),
                "yearOfBirth": int(payload.get("yearOfBirth") or 0),
            }
            if abhaNumber:
                abdmPayload["abhaNumber"] = int(abhaNumber) if abhaNumber.isdigit() else abhaNumber
            overrideHeaders = {"REQUEST-ID": requestId} if requestId else None
            await self.abdmClient.hipPost("hipGenerateToken", abdmPayload, extraHeaders=overrideHeaders, hipId=hipId)
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatched", EventType.LINK_TOKEN_REQUESTED.value, {"step": "generateLinkToken"})
        except Exception as exc:
            self.logger.logError("dispatchLinkTokenFailed", exc, hospitalId=hospitalId, trackingId=trackingId)
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatchFailed", EventType.LINK_TOKEN_REQUESTED.value, {"error": str(exc)[:500]})

    async def _dispatchLinkCareContexts(self, hospitalId: str, trackingId: str, payload: dict[str, Any], requestId: str = "") -> None:
        try:
            abhaNumber = str(payload.get("abhaNumber") or "").replace("-", "")
            abhaAddress = str(payload.get("abhaAddress") or "")
            linkToken = str(payload.get("linkToken") or "")
            patientReference = str(payload.get("patientReference") or "")
            careContexts: list[dict[str, Any]] = payload.get("careContexts") or []

            for ctx in careContexts:
                careContextReference = str(ctx.get("reference") or "")
                temporaryDocument = self.storeTemporaryCareContextDocument(hospitalId, trackingId, careContextReference, ctx)
                temporaryExpiresAt = DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400
                self.dbService.putCareContext(hospitalId, {
                    "patientId": patientReference,
                    "careContextReference": careContextReference,
                    "display": str(ctx.get("display") or ""),
                    "hiTypes": ctx.get("hiTypes") or [],
                    "abhaAddress": abhaAddress,
                    "abhaNumber": abhaNumber or None,
                    "hipId": str(payload.get("hipId") or ""),
                    "clinicalPayload": ctx.get("clinicalPayload") or {},
                    "documentTitle": ctx.get("documentTitle") or None,
                    "documentContentType": ctx.get("documentContentType") or None,
                    "temporaryCareContext": True,
                    "temporaryCareContextTrackingId": trackingId,
                    "temporaryCareContextExpiresAt": temporaryExpiresAt,
                    "expiresAt": temporaryExpiresAt,
                    **temporaryDocument,
                })

            careContextArray = [
                {"referenceNumber": str(ctx.get("reference") or ""), "display": str(ctx.get("display") or "")}
                for ctx in careContexts
            ]
            allHiTypes: list[str] = []
            for ctx in careContexts:
                for ht in (ctx.get("hiTypes") or []):
                    if ht not in allHiTypes:
                        allHiTypes.append(str(ht))
            abdmPayload: dict[str, Any] = {
                "abhaAddress": abhaAddress,
                "patient": [
                    {
                        "referenceNumber": patientReference,
                        "display": patientReference,
                        "careContexts": careContextArray,
                        "hiType": allHiTypes[0] if allHiTypes else "",
                        "count": len(careContextArray),
                    }
                ],
            }
            if abhaNumber:
                abdmPayload["abhaNumber"] = abhaNumber
            hipId = str(payload.get("hipId") or "")
            extraHeaders: dict[str, str] = {}
            if requestId:
                extraHeaders["REQUEST-ID"] = requestId
            if linkToken:
                extraHeaders["X-link-token"] = linkToken
            await self.abdmClient.hipPost("hipLinkCareContext", abdmPayload, extraHeaders or None, hipId=hipId)
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatched", EventType.CARE_CONTEXT_LINKED.value, {"step": "linkCareContext"})
        except Exception as exc:
            self.logger.logError("dispatchLinkCareContextsFailed", exc, hospitalId=hospitalId, trackingId=trackingId)
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatchFailed", EventType.CARE_CONTEXT_LINKED.value, {"error": str(exc)[:500]})

    def storeTemporaryCareContextDocument(
        self,
        hospitalId: str,
        trackingId: str,
        careContextReference: str,
        careContext: dict[str, Any],
    ) -> dict[str, Any]:
        documentData = careContext.get("documentData")
        if not documentData:
            return {}
        bucket = self.settings.encryptedRecordsBucket or self.settings.callbackBodyBucket
        if not bucket:
            raise RuntimeError("Temporary care-context document bucket is not configured")
        documentText = str(documentData)
        eventId = AbdmCryptoService.newEventId()
        safeReference = self.safeS3Segment(careContextReference)
        s3Key = f"temporary-care-contexts/{DateTimeUtils.utcDatePath()}/{hospitalId}/{safeReference}/{trackingId}-{eventId}.json"
        storedAt = DateTimeUtils.utcnowIso()
        expiresAt = DateTimeUtils.epochSeconds() + self.settings.requestTtlDays * 86400
        self.awsService.putJsonObject(bucket, s3Key, {
            "hospitalId": hospitalId,
            "trackingId": trackingId,
            "careContextReference": careContextReference,
            "documentData": documentText,
            "documentTitle": careContext.get("documentTitle") or None,
            "documentContentType": careContext.get("documentContentType") or None,
            "storedAt": storedAt,
            "expiresAt": expiresAt,
        })
        return {
            "temporaryDocumentBucket": bucket,
            "temporaryDocumentS3Key": s3Key,
            "temporaryDocumentStoredAt": storedAt,
            "temporaryDocumentExpiresAt": expiresAt,
            "documentDataStoredTemporarily": True,
            "documentDataSha256": HashUtils.sha256Text(documentText),
            "documentDataBytes": len(documentText.encode("utf-8")),
        }

    async def _dispatchConsentInit(self, hospitalId: str, trackingId: str, requestId: str, payload: dict[str, Any], hiuId: str) -> None:
        try:
            purpose = payload.get("purpose") if isinstance(payload.get("purpose"), dict) else {}
            requester = payload.get("requester") if isinstance(payload.get("requester"), dict) else {}
            dateRange = payload.get("dateRange") if isinstance(payload.get("dateRange"), dict) else {}
            permission = payload.get("permission") if isinstance(payload.get("permission"), dict) else {}
            abdmPayload: dict[str, Any] = {
                "requestId": requestId,
                "timestamp": DateTimeUtils.utcnowIso(),
                "consent": {
                    "purpose": {
                        "text": str(purpose.get("text") or ""),
                        "code": str(purpose.get("code") or ""),
                        "refUri": str(purpose.get("refUri") or ""),
                    },
                    "patient": {"id": str(payload.get("abhaAddress") or "")},
                    "hiu": {"id": hiuId},
                    "hip": None,
                    "careContexts": None,
                    "requester": {
                        "name": str(requester.get("name") or ""),
                        "identifier": {
                            "type": str(requester.get("type") or ""),
                            "value": str(requester.get("value") or ""),
                            "system": str(requester.get("system") or ""),
                        },
                    },
                    "hiTypes": list(payload.get("hiTypes") or []),
                    "permission": {
                        "accessMode": str(permission.get("accessMode") or "VIEW"),
                        "dateRange": {
                            "from": str(dateRange.get("from") or ""),
                            "to": str(dateRange.get("to") or ""),
                        },
                        "dataEraseAt": str(permission.get("dataEraseAt") or dateRange.get("to") or ""),
                        "frequency": {
                            "unit": str((permission.get("frequency") or {}).get("unit") or "HOUR"),
                            "value": int((permission.get("frequency") or {}).get("value") or 0),
                            "repeats": int((permission.get("frequency") or {}).get("repeats") or 0),
                        },
                    },
                },
            }
            # ABDM v3 correlates callbacks by requestId — the REQUEST-ID header must match the body
            await self.abdmClient.hiuPost("consentInit", abdmPayload, extraHeaders={"REQUEST-ID": requestId}, hiuId=hiuId)
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatched", EventType.CONSENT_REQUESTED.value, {"step": "consentInit", "requestId": requestId})
        except Exception as exc:
            self.logger.logError("dispatchConsentInitFailed", exc, hospitalId=hospitalId, trackingId=trackingId, upstream=getattr(exc, "details", None))
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatchFailed", EventType.CONSENT_REQUESTED.value, self._dispatchErrorDetails(exc))

    async def _dispatchHealthInfoRequest(self, hospitalId: str, trackingId: str, payload: dict[str, Any], hiuId: str) -> None:
        try:
            dateRange = payload.get("dateRange") if isinstance(payload.get("dateRange"), dict) else {}
            keyMaterial = payload.get("keyMaterial") if isinstance(payload.get("keyMaterial"), dict) else {}
            dataPushUrl, dataPushTarget = self._resolveDataPushUrl(hospitalId, payload)
            abdmPayload: dict[str, Any] = {
                "hiRequest": {
                    "consent": {"id": str(payload.get("consentId") or "")},
                    "dateRange": {"from": str(dateRange.get("from") or ""), "to": str(dateRange.get("to") or "")},
                    "dataPushUrl": dataPushUrl,
                    "keyMaterial": keyMaterial,
                }
            }
            await self.abdmClient.hiuPost("healthInformationRequest", abdmPayload, hiuId=hiuId)
            self.requestLogService.updateStatus(
                hospitalId, trackingId, "dispatched", EventType.HEALTH_INFORMATION_REQUESTED.value,
                {"step": "healthInfoRequest", "transactionId": str(payload.get("transactionId") or ""), "dataPushTarget": dataPushTarget}
            )
        except Exception as exc:
            self.logger.logError("dispatchHealthInfoRequestFailed", exc, hospitalId=hospitalId, trackingId=trackingId, upstream=getattr(exc, "details", None))
            self.requestLogService.updateStatus(hospitalId, trackingId, "dispatchFailed", EventType.HEALTH_INFORMATION_REQUESTED.value, self._dispatchErrorDetails(exc))

    @staticmethod
    def _dispatchErrorDetails(exc: Exception) -> dict[str, Any]:
        """Keep ABDM's actual rejection (status code + body) visible in the status store."""
        details: dict[str, Any] = {"error": str(exc)[:500]}
        upstream = getattr(exc, "details", None)
        if isinstance(upstream, dict) and upstream:
            details["upstream"] = upstream
        return details

    async def checkConsentStatus(self, hiuId: str, requestBody: ConsentStatusRequest) -> dict[str, Any]:
        """Poll ABDM for the status of a consent request (REQUESTED / GRANTED / DENIED / EXPIRED)."""
        requestId = AbdmCryptoService.newRequestId()
        payload: dict[str, Any] = {
            "requestId": requestId,
            "timestamp": DateTimeUtils.utcnowIso(),
            "consentRequestId": requestBody.consentRequestId,
        }
        return await self.abdmClient.hiuPost("consentStatus", payload, extraHeaders={"REQUEST-ID": requestId}, hiuId=hiuId)

    async def fetchConsentArtefact(self, hiuId: str, requestBody: ConsentFetchRequest) -> dict[str, Any]:
        """Fetch the full consent artefact from ABDM by artefact ID."""
        requestId = AbdmCryptoService.newRequestId()
        payload: dict[str, Any] = {
            "requestId": requestId,
            "timestamp": DateTimeUtils.utcnowIso(),
            "consentId": requestBody.consentId,
        }
        return await self.abdmClient.hiuPost("consentFetch", payload, extraHeaders={"REQUEST-ID": requestId}, hiuId=hiuId)

    def _resolveDataPushUrl(self, hospitalId: str, payload: dict[str, Any]) -> tuple[str, str]:
        """Resolve where the HIP should push encrypted data: explicit request value,
        then the hospital's registered dataPushUrl, then Sahai's own /data endpoint."""
        dataPushUrl = str(payload.get("dataPushUrl") or "").rstrip("/")
        if dataPushUrl:
            return dataPushUrl, "request"
        profile = self.dbService.getHospitalProfile(hospitalId) or {}
        dataPushUrl = str(profile.get("dataPushUrl") or "").strip().rstrip("/")
        if dataPushUrl:
            return dataPushUrl, "registered"
        dataPushUrl = str(self.settings.selfDataEndpointUrl or "").rstrip("/")
        if dataPushUrl:
            return dataPushUrl, "sahai"
        raise RuntimeError("dataPushUrl is required for health information request but is not configured")

    def decryptHealthInformation(self, hospitalId: str, apiKeyHash: str, requestBody: HealthInformationDecryptRequest) -> dict[str, Any]:
        """Decrypt an ABDM data push the hospital received at its own dataPushUrl.
        The ECDH key session is looked up server-side and never leaves this backend.
        Nothing is stored — the plaintext is returned to the caller only."""
        payload = requestBody.model_dump(mode="json")
        transactionId = str(payload.get("transactionId") or "").strip()
        consentId = str(payload.get("consentId") or "")
        if not transactionId:
            raise AppError(422, ErrorCode.INVALID_REQUEST, "transactionId is required so the push can be matched to its ECDH key session")
        matched = self.requestLogService.findByCorrelationIds({"transactionId": transactionId})
        if not matched or str(matched.get("hospitalId") or "") != hospitalId:
            raise AppError(
                404,
                ErrorCode.INVALID_REQUEST,
                "No health-information request matches this transactionId for this hospital (the key session may have expired)",
            )
        if str(matched.get("flowType") or "") != ExternalOperation.REQUEST_HEALTH_INFORMATION.value:
            raise AppError(404, ErrorCode.INVALID_REQUEST, "transactionId does not belong to a health-information request")
        matchedConsentId = str(matched.get("consentId") or "")
        if consentId and matchedConsentId and consentId != matchedConsentId:
            raise AppError(422, ErrorCode.INVALID_REQUEST, "consentId does not match the transactionId key session")
        requestPayload = matched.get("requestPayload") if isinstance(matched.get("requestPayload"), dict) else {}
        patientContext = self.buildPatientContext(requestPayload)
        keySession = requestPayload.get("keySession") if isinstance(requestPayload.get("keySession"), dict) else {}
        if not keySession.get("privateKey") or not keySession.get("nonce"):
            raise AppError(410, ErrorCode.DATA_DECRYPTION_FAILED, "The decryption key session for this request is no longer available")
        keyMaterial = payload.get("keyMaterial") if isinstance(payload.get("keyMaterial"), dict) else {}
        dhPublicKey = keyMaterial.get("dhPublicKey") if isinstance(keyMaterial.get("dhPublicKey"), dict) else {}
        theirPublicKey = str(dhPublicKey.get("keyValue") or "")
        theirNonce = str(keyMaterial.get("nonce") or "")
        if not theirPublicKey or not theirNonce:
            raise AppError(422, ErrorCode.INVALID_REQUEST, "keyMaterial.dhPublicKey.keyValue and keyMaterial.nonce from the HIP's push are required")
        trackingId = str(matched.get("trackingId") or "")
        entries: list[dict[str, Any]] = []
        decryptedCount = 0
        errors: list[dict[str, str]] = []
        for index, entry in enumerate(payload.get("entries") or []):
            entryOut: dict[str, Any] = {
                "careContextReference": str(entry.get("careContextReference") or ""),
                "media": str(entry.get("media") or "application/fhir+json"),
            }
            try:
                plaintext = AbdmCryptoService.ecdhDecrypt(
                    str(entry.get("content") or ""),
                    str(keySession.get("privateKey") or ""),
                    str(keySession.get("nonce") or ""),
                    theirPublicKey,
                    theirNonce,
                )
                try:
                    entryOut["fhir"] = JsonUtils.loadsObject(plaintext)
                except Exception:
                    entryOut["raw"] = plaintext
                decryptedCount += 1
            except Exception as exc:
                entryOut["error"] = f"entry[{index}] could not be decrypted: {exc}"
                errors.append({"code": ErrorCode.DATA_DECRYPTION_FAILED.value, "message": entryOut["error"]})
            entries.append(entryOut)
        self.dbService.recordAccessAudit(hospitalId, "healthInformationDecrypted", {
            "trackingId": trackingId,
            "transactionId": transactionId,
            "consentId": consentId,
            "patientReference": patientContext.get("patientReference") or "",
            "entryCount": len(entries),
            "decryptedCount": decryptedCount,
            "errorCount": len(errors),
            "apiKeyHash": apiKeyHash,
        })
        return {
            "trackingId": trackingId,
            "transactionId": transactionId,
            "consentId": matchedConsentId or consentId,
            "consentRequestId": str(requestPayload.get("consentRequestId") or ""),
            "consentTrackingId": str(requestPayload.get("consentTrackingId") or ""),
            "patient": patientContext,
            "hiTypes": requestPayload.get("hiTypes") if isinstance(requestPayload.get("hiTypes"), list) else [],
            "dateRange": requestPayload.get("dateRange") if isinstance(requestPayload.get("dateRange"), dict) else {},
            "entryCount": len(entries),
            "decryptedCount": decryptedCount,
            "errors": errors,
            "entries": entries,
        }

    @staticmethod
    def buildPatientContext(requestPayload: dict[str, Any]) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "abhaAddress": str(requestPayload.get("abhaAddress") or ""),
                "patientReference": str(requestPayload.get("patientReference") or ""),
            }.items()
            if value
        }

    # ── shared accept helper ─────────────────────────────────────────────────

    def _acceptAndLog(
        self,
        hospitalId: str,
        idempotencyKey: str,
        flowType: str,
        eventType: str,
        payload: dict[str, Any],
        correlation: dict[str, str] | None = None,
        *,
        idempotencyPayload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str, bool]:
        """Accept a request idempotently.
        Returns (response, trackingId, isReplay). If isReplay is True, do not re-dispatch to ABDM.
        """
        key = self.idempotencyService.requireKey(idempotencyKey)
        replay = self.idempotencyService.replayOrReserve(hospitalId, key, idempotencyPayload or payload)
        if replay:
            trackingId = str(replay.get("trackingId") or "")
            return replay, trackingId, True
        created = self.requestLogService.createAcceptedRequest(hospitalId, flowType, payload, correlation)
        self.requestLogService.updateStatus(hospitalId, created["trackingId"], "accepted", eventType, {"flowType": flowType})
        if correlation:
            try:
                self.correlationDbService.storeCorrelationIds(hospitalId, correlation)
            except Exception as exc:
                self.logger.logError("correlationStoreFailed", exc, hospitalId=hospitalId, flowType=flowType)
        response = AcceptedResponse(trackingId=created["trackingId"], requestId=created["requestId"]).model_dump(mode="json")
        self.idempotencyService.storeResponse(hospitalId, key, response)
        self.logger.logProcess("acceptedWrite", hospitalId=hospitalId, flowType=flowType, trackingId=created["trackingId"])
        return response, created["trackingId"], False

    @staticmethod
    def compactCareContextLinkPayload(payload: dict[str, Any]) -> dict[str, Any]:
        compact = dict(payload)
        compactContexts: list[dict[str, Any]] = []
        for careContext in payload.get("careContexts") or []:
            if not isinstance(careContext, dict):
                continue
            compactContext = {key: value for key, value in careContext.items() if key != "documentData"}
            documentData = careContext.get("documentData")
            if documentData:
                documentText = str(documentData)
                compactContext["documentDataStoredTemporarily"] = True
                compactContext["documentDataSha256"] = HashUtils.sha256Text(documentText)
                compactContext["documentDataBytes"] = len(documentText.encode("utf-8"))
            else:
                compactContext["documentDataStoredTemporarily"] = False
            compactContexts.append(compactContext)
        compact["careContexts"] = compactContexts
        return compact

    @staticmethod
    def safeS3Segment(value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(value or ""))
        return (safe[:200] or "care-context")
