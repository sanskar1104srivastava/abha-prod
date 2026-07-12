from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from common.abdm.abdmClient import AbdmClient
from common.abdm.abdmCryptoService import AbdmCryptoService
from common.abdm.requestLogService import RequestLogService
from common.aws.awsService import AwsService
from common.config.settings import getSettings
from common.constants.errorCodes import ErrorCode
from common.constants.eventTypes import EventType
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.utils.dateTimeUtils import DateTimeUtils
from common.utils.hashUtils import HashUtils
from common.utils.jsonUtils import JsonUtils
from common.utils.networkUtils import NetworkUtils
from modules.dataFlow.constants import DataFlowJobType, DataFlowStatus
from modules.dataFlow.dbService import DataFlowDbService
from modules.dataFlow.requests import DataFlowJobRequest, DataPushRequest
from modules.dataFlow.responses import DataAcceptedResponse, DataJobResponse
from modules.externalApi.apiService import ExternalApiService
from modules.externalApi.requests import HealthInformationRequest


class DataFlowApiService:
    def __init__(
        self,
        dbService: DataFlowDbService | None = None,
        requestLogService: RequestLogService | None = None,
        abdmClient: AbdmClient | None = None,
        awsService: AwsService | None = None,
        externalApiService: ExternalApiService | None = None,
    ) -> None:
        self.dbService = dbService or DataFlowDbService()
        self.requestLogService = requestLogService or RequestLogService()
        self.abdmClient = abdmClient or AbdmClient()
        self.awsService = awsService or AwsService()
        self.externalApiService = externalApiService or ExternalApiService()
        self.settings = getSettings()
        self.logger = LoggingService("dataFlow")

    async def handleInboundDataPush(self, path: str, headers: dict[str, Any], requestBody: DataPushRequest) -> dict[str, Any]:
        payload = requestBody.model_dump(mode="json")
        self.logger.logInput("handleInboundDataPush", headers=headers, body=payload)
        dataFlowId = AbdmCryptoService.newEventId()
        matchedRequest = self.requestLogService.findByCorrelationIds(
            {
                "transactionId": payload.get("transactionId") or "",
                "consentId": payload.get("consentId") or self.extractConsentId(payload),
            }
        )
        dbItem = self.dbService.storeInboundDataPush(dataFlowId, path, headers, payload, matchedRequest)
        errors: list[dict[str, str]] = []
        decryptedCount = 0
        if matchedRequest:
            decryptedCount, errors = self.decryptAndStoreEntries(dataFlowId, matchedRequest, payload)
            status = DataFlowStatus.DECRYPTED.value if decryptedCount else DataFlowStatus.ENCRYPTED_STORED.value
            hospitalId = str(matchedRequest["hospitalId"])
            trackingId = str(matchedRequest.get("trackingId") or "")
            self.requestLogService.updateStatus(
                hospitalId,
                trackingId,
                status,
                EventType.HEALTH_INFORMATION_RECEIVED.value,
                {"dataFlowId": dataFlowId, "decryptedCount": decryptedCount, "errors": errors},
            )
            if self.settings.webhookEventsQueueUrl:
                self.awsService.sendQueueMessage(self.settings.webhookEventsQueueUrl, {
                    "eventId": dataFlowId,
                    "eventType": EventType.HEALTH_INFORMATION_RECEIVED.value,
                    "hospitalId": hospitalId,
                    "trackingId": trackingId,
                    "payload": {
                        "encryptedS3Key": str(dbItem.get("encryptedS3Key") or ""),
                        "transactionId": str(payload.get("transactionId") or ""),
                        "entryCount": len(payload.get("entries") or []),
                    },
                })
        else:
            status = DataFlowStatus.ENCRYPTED_STORED.value
            trackingId = None
        return DataAcceptedResponse(
            dataFlowId=dataFlowId,
            trackingId=trackingId,
            status=status,
            encryptedCount=len(payload.get("entries") or []),
            decryptedCount=decryptedCount,
            errors=errors,
        ).model_dump(mode="json")

    def decryptAndStoreEntries(
        self,
        dataFlowId: str,
        matchedRequest: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[int, list[dict[str, str]]]:
        requestPayload = matchedRequest.get("requestPayload") if isinstance(matchedRequest.get("requestPayload"), dict) else {}
        keySession = requestPayload.get("keySession") if isinstance(requestPayload.get("keySession"), dict) else {}
        keyMaterial = payload.get("keyMaterial") if isinstance(payload.get("keyMaterial"), dict) else {}
        theirPublicKey = str(((keyMaterial.get("dhPublicKey") or {}).get("keyValue") if isinstance(keyMaterial.get("dhPublicKey"), dict) else "") or "")
        theirNonce = str(keyMaterial.get("nonce") or "")
        if not keySession or not theirPublicKey or not theirNonce:
            return 0, [{"code": ErrorCode.DATA_DECRYPTION_FAILED.value, "message": "Key material is missing for data push"}]
        hospitalId = str(matchedRequest["hospitalId"])
        trackingId = str(matchedRequest["trackingId"])
        decryptedCount = 0
        errors: list[dict[str, str]] = []
        for index, entry in enumerate(payload.get("entries") or []):
            try:
                plaintext = AbdmCryptoService.ecdhDecrypt(
                    str(entry.get("content") or ""),
                    str(keySession.get("privateKey") or ""),
                    str(keySession.get("nonce") or ""),
                    theirPublicKey,
                    theirNonce,
                )
                decryptedPayload = JsonUtils.loadsObject(plaintext)
                recordId = AbdmCryptoService.newEventId()
                self.dbService.storeDecryptedRecord(
                    hospitalId,
                    trackingId,
                    dataFlowId,
                    recordId,
                    {**entry, "transactionId": payload.get("transactionId") or ""},
                    decryptedPayload,
                )
                decryptedCount += 1
            except Exception as exc:
                errors.append({"code": ErrorCode.DATA_DECRYPTION_FAILED.value, "message": f"entry[{index}] {exc}"})
        return decryptedCount, errors

    async def handleJob(self, requestBody: DataFlowJobRequest) -> dict[str, Any]:
        if requestBody.jobType == DataFlowJobType.HIP_HEALTH_INFORMATION_REQUEST.value:
            return await self.processHipHealthInformationRequest(requestBody)
        if requestBody.jobType == DataFlowJobType.HIU_HEALTH_INFORMATION_REQUEST.value:
            return await self.processHiuHealthInformationRequest(requestBody)
        response = DataJobResponse(
            jobId=requestBody.jobId,
            trackingId=requestBody.trackingId,
            status=DataFlowStatus.SKIPPED.value,
            errors=[{"code": ErrorCode.INVALID_REQUEST.value, "message": "Unsupported data-flow job type"}],
        )
        return response.model_dump(mode="json")

    async def processHiuHealthInformationRequest(self, requestBody: DataFlowJobRequest) -> dict[str, Any]:
        payload = requestBody.payload if isinstance(requestBody.payload, dict) else {}
        consentId = str(payload.get("consentId") or requestBody.correlationIds.get("consentId") or "").strip()
        hiuId = str(payload.get("hiuId") or requestBody.correlationIds.get("hiuId") or "").strip()
        dateRange = payload.get("dateRange") if isinstance(payload.get("dateRange"), dict) else {}
        hiTypes = payload.get("hiTypes") if isinstance(payload.get("hiTypes"), list) else []
        if not consentId or not hiuId or not dateRange:
            result = DataJobResponse(
                jobId=requestBody.jobId,
                trackingId=requestBody.trackingId,
                status=DataFlowStatus.FAILED.value,
                errors=[{"code": ErrorCode.INVALID_REQUEST.value, "message": "Missing consentId, hiuId, or dateRange"}],
            ).model_dump(mode="json")
            self.dbService.storeJobResult(requestBody.hospitalId, requestBody.trackingId, requestBody.jobId, result)
            return result
        idempotencyKey = f"auto-hi-{requestBody.trackingId}-{consentId}"
        try:
            healthInfoResponse = await self.externalApiService.requestHealthInformation(
                requestBody.hospitalId,
                hiuId,
                idempotencyKey,
                HealthInformationRequest(
                    consentId=consentId,
                    hiuId=hiuId,
                    dateRange=dateRange,
                    abhaAddress=str(payload.get("abhaAddress") or "") or None,
                    patientReference=str(payload.get("patientReference") or "") or None,
                    consentRequestId=str(payload.get("consentRequestId") or "") or None,
                    consentTrackingId=str(payload.get("consentTrackingId") or requestBody.trackingId or "") or None,
                    hiTypes=hiTypes,
                ),
            )
            result = DataJobResponse(
                jobId=requestBody.jobId,
                trackingId=requestBody.trackingId,
                status=DataFlowStatus.ACCEPTED.value,
            ).model_dump(mode="json")
            result["healthInformation"] = healthInfoResponse
            self.dbService.storeJobResult(requestBody.hospitalId, requestBody.trackingId, requestBody.jobId, result)
            return result
        except Exception as exc:
            result = DataJobResponse(
                jobId=requestBody.jobId,
                trackingId=requestBody.trackingId,
                status=DataFlowStatus.FAILED.value,
                errors=[{"code": ErrorCode.UPSTREAM_ERROR.value, "message": str(exc)[:500]}],
            ).model_dump(mode="json")
            self.dbService.storeJobResult(requestBody.hospitalId, requestBody.trackingId, requestBody.jobId, result)
            return result

    async def processHipHealthInformationRequest(self, requestBody: DataFlowJobRequest) -> dict[str, Any]:
        payload = requestBody.payload
        hiRequest = payload.get("hiRequest") if isinstance(payload.get("hiRequest"), dict) else {}
        transactionId = str(payload.get("transactionId") or hiRequest.get("transactionId") or requestBody.correlationIds.get("transactionId") or "")
        requestId = str(payload.get("requestId") or requestBody.correlationIds.get("requestId") or "")
        consent = hiRequest.get("consent") if isinstance(hiRequest.get("consent"), dict) else {}
        consentId = str(consent.get("id") or requestBody.correlationIds.get("consentId") or "")
        dataPushUrl = NetworkUtils.validateExternalHttpsUrl(str(hiRequest.get("dataPushUrl") or ""))
        keyMaterial = hiRequest.get("keyMaterial") if isinstance(hiRequest.get("keyMaterial"), dict) else {}
        theirPublicKey = str(((keyMaterial.get("dhPublicKey") or {}).get("keyValue") if isinstance(keyMaterial.get("dhPublicKey"), dict) else "") or "")
        theirNonce = str(keyMaterial.get("nonce") or "")
        if not transactionId or not theirPublicKey or not theirNonce:
            raise AppError(400, ErrorCode.INVALID_REQUEST, "HIP health-information/request is missing transactionId or keyMaterial")
        privateKeyB64, publicKeyB64, nonceB64 = AbdmCryptoService.generateEcdhKeypairForPeer(theirPublicKey)
        senderCurve = "Curve25519" if len(base64.b64decode(theirPublicKey)) == 32 else "curve25519"
        senderKeyMaterial = AbdmCryptoService.keyMaterial(publicKeyB64, nonceB64, self.settingsForExpiry(), senderCurve)
        errors: list[dict[str, str]] = []
        careContextReferences = self.extractCareContextReferences(hiRequest)
        ackStatus = await self.ackHipHealthInformationRequest(transactionId, requestId, careContextReferences)
        if ackStatus.startswith("failed:"):
            errors.append({"code": ErrorCode.UPSTREAM_ERROR.value, "message": ackStatus})
        entries = []
        usedCareContexts: list[tuple[str, dict[str, Any]]] = []
        for careContextReference in careContextReferences:
            careContext = self.dbService.getCareContext(requestBody.hospitalId, careContextReference)
            if not careContext:
                errors.append({"code": ErrorCode.CARE_CONTEXT_NOT_REGISTERED.value, "message": f"Care context not found: {careContextReference}"})
                continue
            try:
                careContext = self.dbService.hydrateTemporaryCareContextDocument(careContext)
            except Exception as exc:
                self.logger.logError("temporaryCareContextHydrationFailed", exc, hospitalId=requestBody.hospitalId, careContextReference=careContextReference)
                errors.append({"code": ErrorCode.INTERNAL_ERROR.value, "message": f"Temporary care context document could not be loaded: {careContextReference}"})
                continue
            plaintextPayload = self.buildFhirPayload(requestBody.hospitalId, transactionId, careContext)
            plaintext = JsonUtils.dumps(plaintextPayload)
            encryptedContent = AbdmCryptoService.ecdhEncrypt(plaintext, privateKeyB64, nonceB64, theirPublicKey, theirNonce)
            entries.append(
                {
                    "content": encryptedContent,
                    "media": "application/fhir+json",
                    "checksum": HashUtils.md5Text(plaintext),
                    "careContextReference": careContextReference,
                }
            )
            usedCareContexts.append((careContextReference, careContext))
        if not entries:
            result = DataJobResponse(
                jobId=requestBody.jobId,
                trackingId=requestBody.trackingId,
                status=DataFlowStatus.FAILED.value,
                ackStatus=ackStatus,
                errors=errors or [{"code": ErrorCode.INVALID_REQUEST.value, "message": "No care contexts were available for push"}],
            ).model_dump(mode="json")
            self.dbService.storeJobResult(requestBody.hospitalId, requestBody.trackingId, requestBody.jobId, result)
            return result
        pushStatusCode = await self.postDataPush(dataPushUrl, transactionId, entries, senderKeyMaterial)
        notifyStatus = await self.notifyAbdmHealthInformation(consentId, transactionId, entries, pushStatusCode)
        cleanupStatus = self.cleanupTemporaryCareContexts(requestBody.hospitalId, usedCareContexts) if pushStatusCode < 400 else []
        result = DataJobResponse(
            jobId=requestBody.jobId,
            trackingId=requestBody.trackingId,
            status=DataFlowStatus.PUSHED.value if pushStatusCode < 400 else DataFlowStatus.FAILED.value,
            ackStatus=ackStatus,
            pushedEntries=len(entries),
            pushStatusCode=pushStatusCode,
            notifyStatus=notifyStatus,
            cleanupStatus=cleanupStatus,
            errors=errors,
        ).model_dump(mode="json")
        self.dbService.storeJobResult(requestBody.hospitalId, requestBody.trackingId, requestBody.jobId, result)
        self.requestLogService.updateStatus(
            requestBody.hospitalId,
            requestBody.trackingId,
            str(result["status"]),
            EventType.HEALTH_INFORMATION_PUSHED.value,
            result,
        )
        return result

    def cleanupTemporaryCareContexts(self, hospitalId: str, careContexts: list[tuple[str, dict[str, Any]]]) -> list[dict[str, str]]:
        cleanupStatus: list[dict[str, str]] = []
        for careContextReference, careContext in careContexts:
            try:
                status = self.dbService.deleteTemporaryCareContext(hospitalId, careContextReference, careContext)
            except Exception as exc:
                self.logger.logError("temporaryCareContextCleanupFailed", exc, hospitalId=hospitalId, careContextReference=careContextReference)
                status = f"failed:{str(exc)[:200]}"
            cleanupStatus.append({"careContextReference": careContextReference, "status": status})
        return cleanupStatus

    async def ackHipHealthInformationRequest(self, transactionId: str, requestId: str, careContextReferences: list[str]) -> str:
        if not requestId:
            return "skipped:missing-request-id"
        hiRequest: dict[str, Any] = {
            "transactionId": transactionId,
            "sessionStatus": "ACKNOWLEDGED",
        }
        if careContextReferences:
            hiRequest["careContextsStatus"] = [
                {"careContextReference": ref, "hiStatus": "OK"}
                for ref in careContextReferences
            ]
        payload = {
            "hiRequest": hiRequest,
            "response": {"requestId": requestId},
        }
        try:
            await self.abdmClient.hipPost("healthInformationHipOnRequest", payload)
            return "sent"
        except Exception as exc:
            self.logger.logError("healthInformationOnRequestAckFailed", exc, transactionId=transactionId, requestId=requestId)
            return f"failed:{str(exc)[:300]}"

    async def postDataPush(self, dataPushUrl: str, transactionId: str, entries: list[dict[str, Any]], keyMaterial: dict[str, Any]) -> int:
        payload = {
            "pageNumber": 1,
            "pageCount": 1,
            "transactionId": transactionId,
            "entries": entries,
            "keyMaterial": keyMaterial,
        }
        headers = {
            "Content-Type": "application/json",
            "REQUEST-ID": AbdmCryptoService.newRequestId(),
            "TIMESTAMP": DateTimeUtils.utcnowIso(),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(dataPushUrl, json=payload, headers=headers)
        return response.status_code

    async def notifyAbdmHealthInformation(self, consentId: str, transactionId: str, entries: list[dict[str, Any]], pushStatusCode: int) -> str:
        if not self.settings.abdmGatewayToken:
            return "skipped"
        status = "TRANSFERRED" if pushStatusCode < 400 else "FAILED"
        payload = {
            "notification": {
                "consentId": consentId,
                "transactionId": transactionId,
                "doneAt": self.settingsForExpiry(),
                "notifier": {"type": "HIP", "id": self.settings.abdmHipId},
                "statusNotification": {
                    "sessionStatus": status,
                    "hipId": self.settings.abdmHipId,
                    "statusResponses": [
                        {
                            "careContextReference": str(entry.get("careContextReference") or ""),
                            "hiStatus": "OK" if status == "TRANSFERRED" else "ERRORED",
                            "description": "Data transferred successfully" if status == "TRANSFERRED" else "Data transfer failed",
                        }
                        for entry in entries
                    ],
                },
            }
        }
        await self.abdmClient.postGatewayEndpoint(
            "healthInformationNotify",
            payload,
            {
                "Authorization": f"Bearer {self.settings.abdmGatewayToken}",
                "X-CM-ID": self.settings.abdmCmId,
                "REQUEST-ID": AbdmCryptoService.newRequestId(),
            },
        )
        return "sent"

    async def handleQueueRecords(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        failures: list[dict[str, str]] = []
        for record in records:
            messageId = str(record.get("messageId") or "")
            try:
                body = json.loads(record.get("body") or "{}")
                await self.handleJob(DataFlowJobRequest.model_validate(body))
            except Exception as exc:
                self.logger.logError("dataFlowRecordFailed", exc, messageId=messageId)
                failures.append({"itemIdentifier": messageId})
        return {"batchItemFailures": failures}

    @staticmethod
    def extractConsentId(payload: dict[str, Any]) -> str:
        consent = payload.get("consent") if isinstance(payload.get("consent"), dict) else {}
        return str(consent.get("id") or "")

    @staticmethod
    def extractCareContextReferences(hiRequest: dict[str, Any]) -> list[str]:
        values = hiRequest.get("careContextReferences")
        if isinstance(values, list):
            return [str(value) for value in values if str(value or "").strip()]
        careContexts = hiRequest.get("careContexts")
        if isinstance(careContexts, list):
            return [str(item.get("referenceNumber") or item.get("careContextReference") or "") for item in careContexts if isinstance(item, dict)]
        return []

    @staticmethod
    def buildFhirPayload(hospitalId: str, transactionId: str, careContext: dict[str, Any]) -> dict[str, Any]:
        from common.constants.hiTypes import (
            PDF_SUPPORTED_HI_TYPES, SNOMED_CODE_BY_HI_TYPE, SNOMED_CODE_DEFAULT,
        )
        hiTypes: list[str] = careContext.get("hiTypes") if isinstance(careContext.get("hiTypes"), list) else []
        hiType = str(hiTypes[0]) if hiTypes else ""
        documentData = str(careContext.get("documentData") or "")
        usePdfMode = hiType in PDF_SUPPORTED_HI_TYPES and bool(documentData)
        if usePdfMode:
            return DataFlowApiService._buildPdfBundle(hospitalId, transactionId, careContext, hiType, documentData)

        clinicalPayload = careContext.get("clinicalPayload") if isinstance(careContext.get("clinicalPayload"), dict) else {}
        snomedCode, snomedDisplay = SNOMED_CODE_BY_HI_TYPE.get(hiType, SNOMED_CODE_DEFAULT)
        clinicalUuid = AbdmCryptoService.newRequestId()
        clinicalResource = DataFlowApiService._clinicalResource(clinicalUuid, careContext, clinicalPayload)
        return DataFlowApiService._buildDocumentBundle(
            hospitalId=hospitalId,
            transactionId=transactionId,
            careContext=careContext,
            hiType=hiType,
            title=str(careContext.get("display") or "Health record"),
            sectionTitle="Clinical Data",
            sectionCode=snomedCode,
            sectionDisplay=snomedDisplay,
            contentResources=[clinicalResource],
        )

    @staticmethod
    def _buildPdfBundle(hospitalId: str, transactionId: str, careContext: dict[str, Any], hiType: str, documentData: str) -> dict[str, Any]:
        from common.constants.hiTypes import (
            DOCUMENT_REFERENCE_PROFILE, SNOMED_CODE_BY_HI_TYPE, SNOMED_CODE_DEFAULT, SNOMED_SYSTEM,
        )
        docRefUuid = AbdmCryptoService.newRequestId()
        snomedCode, snomedDisplay = SNOMED_CODE_BY_HI_TYPE.get(hiType, SNOMED_CODE_DEFAULT)
        contentType = str(careContext.get("documentContentType") or "application/pdf")
        title = str(careContext.get("documentTitle") or careContext.get("display") or "Health document")
        documentReference = {
            "resourceType": "DocumentReference",
            "id": docRefUuid,
            "meta": {"profile": [DOCUMENT_REFERENCE_PROFILE]},
            "status": "current",
            "docStatus": "final",
            "type": {
                "coding": [{"system": SNOMED_SYSTEM, "code": snomedCode, "display": snomedDisplay}],
                "text": title,
            },
            "content": [{
                "attachment": {
                    "contentType": contentType,
                    "language": "en-IN",
                    "data": DataFlowApiService._normalizeAttachmentData(documentData),
                    "title": title,
                    "creation": DataFlowApiService._fhirDateTime(careContext.get("visitDate")),
                }
            }],
        }
        return DataFlowApiService._buildDocumentBundle(
            hospitalId=hospitalId,
            transactionId=transactionId,
            careContext=careContext,
            hiType=hiType,
            title=title,
            sectionTitle="Document Reference",
            sectionCode=snomedCode,
            sectionDisplay=snomedDisplay,
            contentResources=[documentReference],
        )

    @staticmethod
    def _buildDocumentBundle(
        hospitalId: str,
        transactionId: str,
        careContext: dict[str, Any],
        hiType: str,
        title: str,
        sectionTitle: str,
        sectionCode: str,
        sectionDisplay: str,
        contentResources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from common.constants.hiTypes import (
            COMPOSITION_PROFILE_BY_HI_TYPE, DOCUMENT_BUNDLE_PROFILE, SNOMED_CODE_BY_HI_TYPE, SNOMED_CODE_DEFAULT, SNOMED_SYSTEM,
        )
        now = DataFlowApiService._fhirDateTime(
            DataFlowApiService._first(careContext.get("linkedAt"), careContext.get("linked_at"), careContext.get("visitDate"))
        )
        bundleUuid = AbdmCryptoService.newRequestId()
        compositionUuid = AbdmCryptoService.newRequestId()
        patientUuid = AbdmCryptoService.newRequestId()
        practitionerUuid = AbdmCryptoService.newRequestId()
        organizationUuid = AbdmCryptoService.newRequestId()
        encounterUuid = AbdmCryptoService.newRequestId()
        patientRef = DataFlowApiService._fhirRef(patientUuid)
        practitionerRef = DataFlowApiService._fhirRef(practitionerUuid)
        organizationRef = DataFlowApiService._fhirRef(organizationUuid)
        encounterRef = DataFlowApiService._fhirRef(encounterUuid)
        typeCode, typeDisplay = SNOMED_CODE_BY_HI_TYPE.get(hiType, SNOMED_CODE_DEFAULT)

        patient = DataFlowApiService._patientResource(patientUuid, careContext)
        practitioner = DataFlowApiService._practitionerResource(practitionerUuid, careContext)
        organization = DataFlowApiService._organizationResource(organizationUuid, hospitalId, careContext)
        encounter = DataFlowApiService._encounterResource(encounterUuid, patientRef, organizationRef, careContext, hiType, now)
        for resource in [patient, practitioner, organization, encounter]:
            DataFlowApiService._stampResourceMeta(resource, now)

        resolvedContentResources: list[dict[str, Any]] = []
        for resource in contentResources:
            resource = dict(resource)
            resourceId = str(resource.get("id") or AbdmCryptoService.newRequestId())
            resource["id"] = resourceId
            if resource.get("resourceType") == "DocumentReference":
                resource.setdefault("subject", patientRef)
                resource.setdefault("date", now)
                resource.setdefault("author", [practitionerRef])
                resource.setdefault("context", {"encounter": [encounterRef]})
            elif resource.get("resourceType") in {"Observation", "Condition", "MedicationRequest", "DiagnosticReport", "Basic"}:
                resource.setdefault("subject", patientRef)
                if resource.get("resourceType") != "Basic":
                    resource.setdefault("encounter", encounterRef)
            DataFlowApiService._stampResourceMeta(resource, now)
            resolvedContentResources.append(resource)

        sectionEntries = [
            {
                "reference": f"urn:uuid:{resource['id']}",
                "type": str(resource.get("resourceType") or "Resource"),
                "display": str(resource.get("title") or resource.get("resourceType") or title),
            }
            for resource in resolvedContentResources
        ]
        profileUrl = COMPOSITION_PROFILE_BY_HI_TYPE.get(hiType, "")
        composition = {
            "resourceType": "Composition",
            "id": compositionUuid,
            "meta": {
                "versionId": "1",
                "lastUpdated": now,
                **({"profile": [profileUrl]} if profileUrl else {}),
            },
            "language": "en-IN",
            "status": "final",
            "type": {
                "coding": [{"system": SNOMED_SYSTEM, "code": typeCode, "display": typeDisplay}],
                "text": title,
            },
            "subject": patientRef,
            "encounter": encounterRef,
            "date": now,
            "author": [practitionerRef],
            "title": title,
            "custodian": organizationRef,
            "section": [{
                "title": sectionTitle,
                "code": {"coding": [{"system": SNOMED_SYSTEM, "code": sectionCode, "display": sectionDisplay}]},
                "entry": sectionEntries,
            }],
        }
        entries = [
            DataFlowApiService._bundleEntry(compositionUuid, composition),
            DataFlowApiService._bundleEntry(patientUuid, patient),
            DataFlowApiService._bundleEntry(practitionerUuid, practitioner),
            DataFlowApiService._bundleEntry(organizationUuid, organization),
            DataFlowApiService._bundleEntry(encounterUuid, encounter),
            *[DataFlowApiService._bundleEntry(str(resource["id"]), resource) for resource in resolvedContentResources],
        ]
        return {
            "resourceType": "Bundle",
            "id": bundleUuid,
            "meta": {
                "versionId": "1",
                "lastUpdated": now,
                "profile": [DOCUMENT_BUNDLE_PROFILE],
                "security": [{"system": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality", "code": "V", "display": "very restricted"}],
                "tag": [{"system": "sahaiHospitalId", "code": hospitalId}],
            },
            "identifier": {
                "system": "https://ndhm.in/bundle",
                "value": DataFlowApiService._first(careContext.get("careContextReference"), transactionId, bundleUuid),
            },
            "type": "document",
            "timestamp": now,
            "entry": entries,
        }

    @staticmethod
    def _patientResource(patientUuid: str, careContext: dict[str, Any]) -> dict[str, Any]:
        clinicalPayload = careContext.get("clinicalPayload") if isinstance(careContext.get("clinicalPayload"), dict) else {}
        patientPayload = clinicalPayload.get("patient") if isinstance(clinicalPayload.get("patient"), dict) else {}
        consultation = clinicalPayload.get("consultation") if isinstance(clinicalPayload.get("consultation"), dict) else {}
        name = DataFlowApiService._first(
            patientPayload.get("name"),
            patientPayload.get("patient_name"),
            clinicalPayload.get("patientName"),
            consultation.get("patient_name"),
            careContext.get("patientName"),
            careContext.get("patientId"),
            "Unknown",
        )
        resource: dict[str, Any] = {
            "resourceType": "Patient",
            "id": patientUuid,
            "meta": {"profile": [DataFlowApiService._profile("Patient")]},
            "name": [{"text": name}],
            "gender": DataFlowApiService._normalizeGender(
                DataFlowApiService._first(patientPayload.get("gender"), clinicalPayload.get("gender"), consultation.get("gender"))
            ),
        }
        birthDate = DataFlowApiService._normalizeBirthDate(
            DataFlowApiService._first(
                patientPayload.get("birthDate"),
                patientPayload.get("date_of_birth"),
                patientPayload.get("dob"),
                clinicalPayload.get("birthDate"),
                consultation.get("date_of_birth"),
                careContext.get("yearOfBirth"),
            )
        )
        if birthDate:
            resource["birthDate"] = birthDate
        identifiers = []
        abhaAddress = DataFlowApiService._first(careContext.get("abhaAddress"), patientPayload.get("abhaAddress"), clinicalPayload.get("abhaAddress"))
        abhaNumber = DataFlowApiService._first(careContext.get("abhaNumber"), patientPayload.get("abhaNumber"), clinicalPayload.get("abhaNumber"))
        patientId = DataFlowApiService._first(careContext.get("patientId"), patientPayload.get("patientId"), clinicalPayload.get("patientReference"))
        if patientId:
            identifiers.append({
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR", "display": "Medical record number"}]},
                "system": "https://sahai.health/patient-reference",
                "value": patientId,
            })
        if abhaAddress:
            identifiers.append({"system": "https://healthid.ndhm.gov.in", "value": abhaAddress})
        if abhaNumber:
            identifiers.append({"system": "https://healthid.ndhm.gov.in/number", "value": abhaNumber})
        if identifiers:
            resource["identifier"] = identifiers
        return resource

    @staticmethod
    def _practitionerResource(practitionerUuid: str, careContext: dict[str, Any]) -> dict[str, Any]:
        clinicalPayload = careContext.get("clinicalPayload") if isinstance(careContext.get("clinicalPayload"), dict) else {}
        consultation = clinicalPayload.get("consultation") if isinstance(clinicalPayload.get("consultation"), dict) else {}
        practitionerName = DataFlowApiService._first(
            consultation.get("practitioner_name"),
            consultation.get("practitionerName"),
            clinicalPayload.get("practitionerName"),
            "Healthcare Practitioner",
        )
        practitionerId = DataFlowApiService._first(
            consultation.get("practitioner_id"),
            consultation.get("practitionerId"),
            clinicalPayload.get("practitionerId"),
        )
        resource: dict[str, Any] = {
            "resourceType": "Practitioner",
            "id": practitionerUuid,
            "meta": {"profile": [DataFlowApiService._profile("Practitioner")]},
            "name": [{"text": practitionerName}],
        }
        if practitionerId:
            resource["identifier"] = [{"system": "https://hprid.ndhm.gov.in", "value": practitionerId}]
        return resource

    @staticmethod
    def _organizationResource(organizationUuid: str, hospitalId: str, careContext: dict[str, Any]) -> dict[str, Any]:
        clinicalPayload = careContext.get("clinicalPayload") if isinstance(careContext.get("clinicalPayload"), dict) else {}
        consultation = clinicalPayload.get("consultation") if isinstance(clinicalPayload.get("consultation"), dict) else {}
        organizationName = DataFlowApiService._first(
            consultation.get("organization_name"),
            consultation.get("organizationName"),
            clinicalPayload.get("organizationName"),
            careContext.get("hipName"),
            careContext.get("hipId"),
            hospitalId,
        )
        organizationId = DataFlowApiService._first(
            consultation.get("organization_id"),
            consultation.get("organizationId"),
            clinicalPayload.get("organizationId"),
            careContext.get("hipId"),
            hospitalId,
        )
        resource: dict[str, Any] = {
            "resourceType": "Organization",
            "id": organizationUuid,
            "meta": {"profile": [DataFlowApiService._profile("Organization")]},
            "name": organizationName,
        }
        if organizationId:
            resource["identifier"] = [{"system": "https://facilityregistry.ndhm.gov.in", "value": organizationId}]
        return resource

    @staticmethod
    def _encounterResource(
        encounterUuid: str,
        patientRef: dict[str, str],
        organizationRef: dict[str, str],
        careContext: dict[str, Any],
        hiType: str,
        now: str,
    ) -> dict[str, Any]:
        clinicalPayload = careContext.get("clinicalPayload") if isinstance(careContext.get("clinicalPayload"), dict) else {}
        consultation = clinicalPayload.get("consultation") if isinstance(clinicalPayload.get("consultation"), dict) else {}
        encounterClass = {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"}
        start = DataFlowApiService._fhirDateTime(DataFlowApiService._first(careContext.get("visitDate"), consultation.get("date")), now)
        end = start
        if hiType == "DischargeSummary":
            encounterClass = {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter"}
            start = DataFlowApiService._fhirDateTime(
                DataFlowApiService._first(consultation.get("admission_datetime"), consultation.get("admission_date"), careContext.get("admissionDate")),
                now,
            )
            end = DataFlowApiService._fhirDateTime(
                DataFlowApiService._first(consultation.get("discharge_datetime"), consultation.get("discharge_date"), careContext.get("dischargeDate")),
                now,
            )
        return {
            "resourceType": "Encounter",
            "id": encounterUuid,
            "meta": {"profile": [DataFlowApiService._profile("Encounter")]},
            "status": "finished",
            "class": encounterClass,
            "subject": patientRef,
            "period": {"start": start, "end": end},
            "serviceProvider": organizationRef,
        }

    @staticmethod
    def _clinicalResource(resourceId: str, careContext: dict[str, Any], clinicalPayload: dict[str, Any]) -> dict[str, Any]:
        if clinicalPayload.get("resourceType") and str(clinicalPayload.get("resourceType")) not in {"Bundle", "Composition"}:
            resource = dict(clinicalPayload)
            resource["id"] = str(resource.get("id") or resourceId)
            return resource
        resource: dict[str, Any] = {
            "resourceType": "Basic",
            "id": resourceId,
            "code": {"text": "Clinical payload"},
            "created": DataFlowApiService._fhirDateTime(careContext.get("visitDate")),
        }
        if clinicalPayload:
            resource["extension"] = [{
                "url": "https://sahai.health/fhir/StructureDefinition/clinical-payload",
                "valueString": JsonUtils.dumps(clinicalPayload),
            }]
        else:
            resource["code"] = {"text": "Clinical payload unavailable"}
        return resource

    @staticmethod
    def _stampResourceMeta(resource: dict[str, Any], now: str) -> None:
        resource.setdefault("meta", {})
        if isinstance(resource["meta"], dict):
            resource["meta"].setdefault("lastUpdated", now)

    @staticmethod
    def _bundleEntry(resourceId: str, resource: dict[str, Any]) -> dict[str, Any]:
        return {"fullUrl": f"urn:uuid:{resourceId}", "resource": resource}

    @staticmethod
    def _fhirRef(resourceId: str) -> dict[str, str]:
        return {"reference": f"urn:uuid:{resourceId}"}

    @staticmethod
    def _profile(resourceName: str) -> str:
        from common.constants.hiTypes import FHIR_BASE
        return f"{FHIR_BASE}/{resourceName}"

    @staticmethod
    def _normalizeAttachmentData(documentData: str) -> str:
        text = str(documentData or "").strip()
        if text.startswith("data:") and "," in text:
            text = text.split(",", 1)[1]
        compact = "".join(text.split())
        try:
            base64.b64decode(compact, validate=True)
            return compact
        except Exception:
            return base64.b64encode(text.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _normalizeGender(value: str) -> str:
        text = str(value or "").strip().lower()
        if text in {"male", "female", "other", "unknown"}:
            return text
        return {"m": "male", "f": "female", "o": "other"}.get(text[:1], "unknown")

    @staticmethod
    def _normalizeBirthDate(value: str) -> str:
        text = str(value or "").strip()
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
        if len(text) == 4 and text.isdigit():
            return text
        return ""

    @staticmethod
    def _fhirDateTime(value: Any = "", fallback: str = "") -> str:
        text = DataFlowApiService._first(value)
        if not text:
            return fallback or DateTimeUtils.utcnowIso()
        if "T" in text:
            return text
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return f"{text[:10]}T00:00:00Z"
        return fallback or DateTimeUtils.utcnowIso()

    @staticmethod
    def _first(*values: Any) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def settingsForExpiry() -> str:
        return DateTimeUtils.utcIsoAfter(hours=1)
