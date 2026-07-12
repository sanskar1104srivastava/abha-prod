from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request, status

from common.constants.errorCodes import ErrorCode
from common.http.errorHandler import AppError
from common.logging.loggingService import LoggingService
from common.security.apiKeyAuthService import ApiKeyAuthService
from modules.externalApi.apiService import ExternalApiService
from modules.externalApi.requests import (
    CareContextLinkRequest,
    ConsentFetchRequest,
    ConsentRequest,
    ConsentStatusRequest,
    HealthInformationDecryptRequest,
    HealthInformationRequest,
    LinkTokenRequest,
)

router = APIRouter()
apiService = ExternalApiService()
authService = ApiKeyAuthService()
logger = LoggingService("externalApi.routes")


def authenticateRequest(request: Request) -> dict[str, Any]:
    if "hospital_id" in request.query_params or "hospitalId" in request.query_params:
        raise AppError(400, ErrorCode.INVALID_REQUEST, "hospital_id must not be supplied by clients; it is derived from API key")
    context = authService.authenticate(dict(request.headers))
    return context


def resolveHiuId(context: dict[str, Any], bodyHiuId: str | None) -> str:
    """Request-body hiuId wins; the HIU ID registered with the API key is the fallback."""
    hiuId = str(bodyHiuId or "").strip() or str(context.get("hiuId") or "").strip()
    if not hiuId:
        raise AppError(403, ErrorCode.FORBIDDEN, "No HIU ID — pass hiuId in the request body or register one for this hospital")
    return hiuId


@router.post("/v1/link-token", status_code=status.HTTP_202_ACCEPTED)
async def requestLinkToken(
    request: Request,
    requestBody: LinkTokenRequest,
    idempotencyKey: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("requestLinkToken", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.requestLinkToken(context["hospitalId"], idempotencyKey or "", requestBody)


@router.post("/v1/care-contexts/link", status_code=status.HTTP_202_ACCEPTED)
async def linkCareContexts(
    request: Request,
    requestBody: CareContextLinkRequest,
    idempotencyKey: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("linkCareContexts", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.linkCareContexts(context["hospitalId"], idempotencyKey or "", requestBody)


@router.post("/v1/consents", status_code=status.HTTP_202_ACCEPTED)
async def requestConsent(
    request: Request,
    requestBody: ConsentRequest,
    idempotencyKey: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("requestConsent", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.requestConsent(context["hospitalId"], resolveHiuId(context, requestBody.hiuId), idempotencyKey or "", requestBody)


@router.post("/v1/health-information", status_code=status.HTTP_202_ACCEPTED)
async def requestHealthInformation(
    request: Request,
    requestBody: HealthInformationRequest,
    idempotencyKey: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("requestHealthInformation", headers=dict(request.headers), body=requestBody.model_dump(mode="json"))
    return await apiService.requestHealthInformation(context["hospitalId"], resolveHiuId(context, requestBody.hiuId), idempotencyKey or "", requestBody)


@router.post("/v1/consents/status")
async def checkConsentStatus(
    request: Request,
    requestBody: ConsentStatusRequest,
) -> dict[str, Any]:
    """
    Poll ABDM for the status of a consent request.

    Returns REQUESTED / GRANTED / DENIED / EXPIRED. This is a direct ABDM
    call — use it when you need the status immediately rather than waiting
    for the consent webhook to arrive.
    """
    context = authenticateRequest(request)
    logger.logInput("checkConsentStatus", headers=dict(request.headers), body=requestBody.model_dump(mode="json"), hospitalId=context["hospitalId"])
    return await apiService.checkConsentStatus(resolveHiuId(context, requestBody.hiuId), requestBody)


@router.post("/v1/consents/fetch")
async def fetchConsentArtefact(
    request: Request,
    requestBody: ConsentFetchRequest,
) -> dict[str, Any]:
    """
    Fetch the full consent artefact from ABDM.

    Use the consentId from the consent-granted webhook to retrieve the
    full artefact including permitted hiTypes, date range, and care contexts.
    """
    context = authenticateRequest(request)
    logger.logInput("fetchConsentArtefact", headers=dict(request.headers), body=requestBody.model_dump(mode="json"), hospitalId=context["hospitalId"])
    return await apiService.fetchConsentArtefact(resolveHiuId(context, requestBody.hiuId), requestBody)


@router.get("/v1/status/{trackingId}")
async def getStatus(request: Request, trackingId: str) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("getStatus", headers=dict(request.headers), body={"trackingId": trackingId}, hospitalId=context["hospitalId"])
    return apiService.getStatus(context["hospitalId"], trackingId)


@router.get("/v1/health-records/{trackingId}")
async def getHealthRecordResult(request: Request, trackingId: str) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("getHealthRecordResult", headers=dict(request.headers), body={"trackingId": trackingId}, hospitalId=context["hospitalId"])
    return apiService.getHealthRecordResult(context["hospitalId"], trackingId)


@router.get("/v1/health-records/{trackingId}/decrypt")
async def getDecryptedRecords(request: Request, trackingId: str) -> dict[str, Any]:
    context = authenticateRequest(request)
    logger.logInput("getDecryptedRecords", headers=dict(request.headers), body={"trackingId": trackingId}, hospitalId=context["hospitalId"])
    return apiService.getDecryptedRecords(context["hospitalId"], trackingId, context["apiKeyHash"])


@router.post("/v1/health-information/decrypt")
async def decryptHealthInformation(
    request: Request,
    requestBody: HealthInformationDecryptRequest,
) -> dict[str, Any]:
    """
    Decrypt an ABDM data push received directly at your registered dataPushUrl.

    Forward the HIP's push payload unchanged (transactionId, entries, keyMaterial).
    The ECDH key session stays on Sahai's side; the decrypted FHIR bundles are
    returned in the response and are not stored by Sahai.
    """
    context = authenticateRequest(request)
    logger.logInput(
        "decryptHealthInformation",
        headers=dict(request.headers),
        body={
            "transactionId": requestBody.transactionId or "",
            "consentId": requestBody.consentId or "",
            "entryCount": len(requestBody.entries),
        },
        hospitalId=context["hospitalId"],
    )
    return apiService.decryptHealthInformation(context["hospitalId"], context["apiKeyHash"], requestBody)
