from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


class BehaviorContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def read(self, relativePath: str) -> str:
        return (self.root / relativePath).read_text(encoding="utf-8")

    def test_external_api_auth_and_idempotency_contract(self) -> None:
        routes = self.read("modules/externalApi/routes.py")
        service = self.read("modules/externalApi/apiService.py")
        requests = self.read("modules/externalApi/requests.py")
        self.assertIn("hospital_id must not be supplied", routes)
        self.assertIn("authService.authenticate", routes)
        self.assertIn('alias="Idempotency-Key"', routes)
        self.assertIn("replayOrReserve", service)
        self.assertIn("storeResponse", service)
        self.assertIn("compactCareContextLinkPayload", service)
        self.assertIn('"consentRequestId": requestId', service)
        self.assertIn('response["consentRequestId"]', service)
        self.assertIn("documentDataSha256", service)
        self.assertIn("storeTemporaryCareContextDocument", service)
        self.assertIn("temporaryDocumentS3Key", service)
        self.assertIn("idempotencyPayload=idempotencyPayload", service)
        self.assertIn('findByCorrelationIds({"transactionId": transactionId})', service)
        self.assertIn("transactionId is required so the push can be matched to its ECDH key session", service)
        self.assertIn("transactionId does not belong to a health-information request", service)
        self.assertIn("patientReference: str = Field(min_length=1", requests)
        self.assertIn('"patient": patientContext', service)
        self.assertNotIn('payload.pop("patientReference"', service)
        self.assertIn("transactionId: str = Field(min_length=1", requests)
        self.assertIn('ConfigDict(extra="forbid")', requests)

    def test_postman_consent_request_uses_fresh_idempotency_key(self) -> None:
        collection = self.read("Sahai_Production_Backend.postman_collection.json")
        self.assertIn('"Idempotency-Key", "value": "con-{{$guid}}"', collection)
        self.assertIn("j.consentRequestId || j.requestId", collection)
        self.assertIn('\\"to\\": \\"{{$isoTimestamp}}\\"', collection)
        self.assertIn('\\"patientReference\\": \\"{{patientReference}}\\"', collection)

    def test_callback_router_correlation_and_queue_contract(self) -> None:
        routes = self.read("modules/callbackRouter/routes.py")
        service = self.read("modules/callbackRouter/apiService.py")
        response = self.read("modules/callbackRouter/responses.py")
        hip = self.read("modules/hip/apiService.py")
        self.assertIn("findByCorrelationIds", service)
        self.assertIn("enqueueWebhookEvent", service)
        self.assertIn("enqueueDataFlowJob", service)
        self.assertIn("health-information/request", service)
        self.assertIn("handleCallbackAsync", routes)
        self.assertIn("ackHipConsentNotifyIfNeeded", service)
        self.assertIn("consentHipOnNotify", service)
        self.assertIn('"response": {"requestId": requestId}', service)
        self.assertIn("enqueueConsentFetchRequestsForConsentArtefacts", service)
        self.assertIn("enqueueHealthInformationRequestForFetchedConsent", service)
        self.assertIn("shouldCreateHealthInformationRequestFromConsentFetch", service)
        self.assertIn("HIU_HEALTH_INFORMATION_REQUEST", service)
        self.assertIn("HIU_CONSENT_FETCH", service)
        requestLogService = self.read("common/abdm/requestLogService.py")
        awsService = self.read("common/aws/awsService.py")
        self.assertIn("recordConsentArtefactIndex", requestLogService)
        self.assertIn("findConsentFetchByRequestId", requestLogService)
        self.assertIn("DelaySeconds", awsService)
        self.assertIn("consentFetchDelaySeconds", service)
        self.assertIn("retryConsentFetchIfTransientArtefactError", service)
        self.assertIn("consentFetchRetryQueued", service)
        self.assertIn("delaySeconds=delaySeconds", service)
        self.assertIn("webhookEventSkipped", service)
        self.assertIn("buildConsentStatusPayload", service)
        self.assertIn('"patientReference"', service)
        self.assertIn('"consentArtefacts"', service)
        self.assertIn("correlationUpdates", service)
        self.assertIn("matchedRequest = {**matchedRequest, **correlationUpdates}", service)
        self.assertIn('"response": {"requestId": requestBody.requestId}', hip)
        self.assertIn("resolveCallbackRequestId", service)
        self.assertIn('loweredHeaders.get("request-id")', service)
        self.assertIn("class CallbackAckResponse", response)
        self.assertNotIn("correlationStatus", response)
        self.assertNotIn("trackingId", response)

    def test_hiu_consent_notify_ack_uses_callback_header_request_id(self) -> None:
        import asyncio

        sys.path.insert(0, str(self.root))
        from common.abdm.callbackCorrelationService import CallbackCorrelationService
        from modules.callbackRouter.apiService import CallbackRouterApiService

        class FakeAbdmClient:
            def __init__(self) -> None:
                self.endpointKey = ""
                self.payload = {}
                self.extraHeaders = {}
                self.hiuId = ""

            async def hiuPost(self, endpointKey, payload, extraHeaders=None, hiuId=""):
                self.endpointKey = endpointKey
                self.payload = payload
                self.extraHeaders = extraHeaders or {}
                self.hiuId = hiuId
                return {}

        class FakeLogger:
            def logError(self, *args, **kwargs):
                raise AssertionError("ack should not fail")

        fakeAbdmClient = FakeAbdmClient()
        service = CallbackRouterApiService.__new__(CallbackRouterApiService)
        service.correlationService = CallbackCorrelationService()
        service.abdmClient = fakeAbdmClient
        service.logger = FakeLogger()

        status = asyncio.run(service.ackHiuConsentNotifyIfNeeded(
            "/callback/api/v3/hiu/consent/request/notify",
            {"request_id": "callback-header-request-id"},
            {"notification": {"consentArtefacts": [{"id": "consent-1"}]}},
            {"hiuId": "HIU-1"},
            "evt-local-callback-id",
        ))

        self.assertEqual("sent:1", status)
        self.assertEqual("consentHiuOnNotify", fakeAbdmClient.endpointKey)
        self.assertEqual("HIU-1", fakeAbdmClient.hiuId)
        self.assertEqual("callback-header-request-id", fakeAbdmClient.payload["response"]["requestId"])
        self.assertNotIn("requestId", fakeAbdmClient.payload)
        self.assertNotIn("timestamp", fakeAbdmClient.payload)
        self.assertTrue(fakeAbdmClient.extraHeaders["REQUEST-ID"])

    def test_consent_fetch_fanout_is_paced(self) -> None:
        from types import SimpleNamespace

        sys.path.insert(0, str(self.root))
        from common.abdm.callbackCorrelationService import CallbackCorrelationService
        from modules.callbackRouter.apiService import CallbackRouterApiService
        from modules.callbackRouter.constants import CallbackJobType

        class FakeAwsService:
            def __init__(self) -> None:
                self.messages: list[tuple[str, dict, int]] = []

            def sendQueueMessage(self, queueUrl, message, delaySeconds=0):
                self.messages.append((queueUrl, message, delaySeconds))
                return {}

        class FakeLogger:
            def logProcess(self, *args, **kwargs):
                pass

        fakeAws = FakeAwsService()
        service = CallbackRouterApiService.__new__(CallbackRouterApiService)
        service.correlationService = CallbackCorrelationService()
        service.awsService = fakeAws
        service.settings = SimpleNamespace(dataFlowJobsQueueUrl="queue-url")
        service.logger = FakeLogger()

        service.enqueueConsentFetchRequestsForConsentArtefacts(
            "hospital-a",
            "trk-1",
            "/callback/api/v3/hiu/consent/request/notify",
            {"hiuId": "HIU-1", "consentRequestId": "crid-1"},
            {"notification": {"consentArtefacts": [{"id": "consent-1"}, {"id": "consent-2"}]}},
            {"requestPayload": {"patientReference": "PAT-1"}},
            "evt-1",
        )

        self.assertEqual([10, 11], [item[2] for item in fakeAws.messages])
        self.assertEqual(CallbackJobType.HIU_CONSENT_FETCH.value, fakeAws.messages[0][1]["jobType"])
        self.assertEqual(0, fakeAws.messages[0][1]["payload"]["consentFetchAttempt"])
        self.assertEqual(1, fakeAws.messages[1][1]["payload"]["consentFetchIndex"])

    def test_transient_consent_fetch_error_is_retried(self) -> None:
        from types import SimpleNamespace

        sys.path.insert(0, str(self.root))
        from modules.callbackRouter.apiService import CallbackRouterApiService
        from modules.callbackRouter.constants import CallbackJobType

        class FakeAwsService:
            def __init__(self) -> None:
                self.message = {}
                self.delaySeconds = 0

            def sendQueueMessage(self, queueUrl, message, delaySeconds=0):
                self.message = message
                self.delaySeconds = delaySeconds
                return {}

        class FakeRequestLogService:
            def findConsentFetchByRequestId(self, requestId):
                self.requestId = requestId
                return {
                    "hospitalId": "hospital-a",
                    "trackingId": "trk-1",
                    "consentId": "consent-1",
                    "consentRequestId": "crid-1",
                    "requestPayload": {
                        "consentId": "consent-1",
                        "hiuId": "HIU-1",
                        "consentRequestId": "crid-1",
                        "consentFetchAttempt": 0,
                    },
                }

        class FakeLogger:
            def logProcess(self, *args, **kwargs):
                pass

        fakeAws = FakeAwsService()
        fakeRequestLog = FakeRequestLogService()
        service = CallbackRouterApiService.__new__(CallbackRouterApiService)
        service.awsService = fakeAws
        service.requestLogService = fakeRequestLog
        service.settings = SimpleNamespace(dataFlowJobsQueueUrl="queue-url")
        service.logger = FakeLogger()

        status = service.retryConsentFetchIfTransientArtefactError(
            "hospital-a",
            "trk-1",
            "/callback/api/v3/hiu/consent/on-fetch",
            {
                "response": {"requestId": "fetch-request-id"},
                "error": {"code": "ABDM-1080: ", "message": "Invalid Consent artefact id"},
            },
            "evt-1",
        )

        self.assertEqual("queued", status)
        self.assertEqual("fetch-request-id", fakeRequestLog.requestId)
        self.assertEqual(30, fakeAws.delaySeconds)
        self.assertEqual(CallbackJobType.HIU_CONSENT_FETCH.value, fakeAws.message["jobType"])
        self.assertEqual(1, fakeAws.message["payload"]["consentFetchAttempt"])
        self.assertEqual("fetch-request-id", fakeAws.message["payload"]["consentFetchRetryForRequestId"])

    def test_callback_correlation_hydrates_callback_hit_to_request_row(self) -> None:
        sys.path.insert(0, str(self.root))
        from common.abdm.requestLogService import RequestLogService

        class FakeDb:
            def __init__(self) -> None:
                self.getKey = {}

            def queryIndex(self, tableName, indexName, keyName, keyValue, limit=20):
                return [
                    {
                        "recordType": "callback",
                        "hospitalId": "hospital-a",
                        "trackingId": "trk-1",
                        "consentRequestId": keyValue,
                    }
                ]

            def getItem(self, tableName, key, consistentRead=False):
                self.getKey = key
                return {
                    "recordType": "request",
                    "hospitalId": "hospital-a",
                    "trackingId": "trk-1",
                    "flowType": "external.consent.request",
                    "requestPayload": {
                        "dateRange": {"from": "2026-01-01T00:00:00.000Z", "to": "2026-07-12T00:00:00.000Z"},
                        "patientReference": "PAT-001",
                    },
                }

        fakeDb = FakeDb()
        matched = RequestLogService(dbService=fakeDb).findByCorrelationIds({"consentRequestId": "abdm-crid"})

        self.assertEqual("request", matched["recordType"])
        self.assertEqual({"pk": "HOSP#hospital-a", "sk": "REQ#trk-1"}, fakeDb.getKey)
        self.assertIn("dateRange", matched["requestPayload"])
        service = self.read("common/abdm/requestLogService.py")
        self.assertNotIn("HIP_ID_INDEX", service)
        self.assertNotIn("HIU_ID_INDEX", service)

    def test_callback_backfill_overwrites_abdm_transaction_id(self) -> None:
        sys.path.insert(0, str(self.root))
        from common.abdm.requestLogService import RequestLogService

        class FakeDb:
            def __init__(self) -> None:
                self.updateExpression = ""
                self.expressionValues = {}

            def updateItem(self, tableName, key, updateExpression, expressionValues, expressionNames=None):
                self.updateExpression = updateExpression
                self.expressionValues = expressionValues
                return {}

        fakeDb = FakeDb()
        RequestLogService(dbService=fakeDb).backfillCorrelation(
            "hospital-a",
            "trk-1",
            {"transactionId": "abdm-txn-1", "consentRequestId": "abdm-crid-1", "consentId": "consent-1"},
        )

        self.assertIn("transactionId = :transactionId", fakeDb.updateExpression)
        self.assertIn("abdmTransactionId = :transactionId", fakeDb.updateExpression)
        self.assertIn("consentRequestId = :consentRequestId", fakeDb.updateExpression)
        self.assertIn("consentId = if_not_exists(consentId, :consentId)", fakeDb.updateExpression)
        self.assertEqual("abdm-txn-1", fakeDb.expressionValues[":transactionId"])
        self.assertEqual("abdm-crid-1", fakeDb.expressionValues[":consentRequestId"])

    def test_data_flow_encrypt_decrypt_contract(self) -> None:
        service = self.read("modules/dataFlow/apiService.py")
        externalService = self.read("modules/externalApi/apiService.py")
        main = self.read("modules/dataFlow/main.py")
        crypto = self.read("common/abdm/abdmCryptoService.py")
        self.assertIn("handleInboundDataPush", service)
        self.assertIn("decryptAndStoreEntries", service)
        self.assertIn("processHipHealthInformationRequest", service)
        self.assertIn("processHiuHealthInformationRequest", service)
        self.assertIn("async def handleQueueEvent", main)
        self.assertIn("DataFlowApiService().handleQueueRecords", main)
        self.assertIn("ensureEventLoop()", main)
        self.assertNotIn("queueService = DataFlowApiService()", main)
        self.assertIn("requestHealthInformation", service)
        self.assertIn("processHiuConsentFetch", service)
        self.assertIn('extraHeaders=extraHeaders', externalService)
        self.assertIn('payload["requestId"] = requestId', externalService)
        self.assertIn('"requestId": requestId', externalService)
        self.assertIn("auto-hi-", service)
        self.assertIn("patientReference=str(payload.get", service)
        self.assertIn("ackHipHealthInformationRequest", service)
        self.assertIn("healthInformationHipOnRequest", service)
        self.assertIn('"response": {"requestId": requestId}', service)
        self.assertIn("hydrateTemporaryCareContextDocument", service)
        self.assertIn("cleanupTemporaryCareContexts", service)
        self.assertIn("deleteTemporaryCareContext", self.read("modules/dataFlow/dbService.py"))
        self.assertIn("postDataPush", service)
        self.assertIn("TIMESTAMP", service)
        self.assertIn("HashUtils.md5Text", service)
        self.assertIn("ecdhDecrypt", crypto)
        self.assertIn("ecdhEncrypt", crypto)
        self.assertIn("generateFideliusEcdhKeypair", crypto)
        self.assertIn("generateEcdhKeypairForPeer", crypto)

    def test_abdm_crypto_supports_raw_and_fidelius_roundtrips(self) -> None:
        sys.path.insert(0, str(self.root))
        from common.abdm.abdmCryptoService import AbdmCryptoService

        rawPrivate, rawPublic, rawNonce = AbdmCryptoService.generateRawEcdhKeypair()
        rawPeerPrivate, rawPeerPublic, rawPeerNonce = AbdmCryptoService.generateEcdhKeypairForPeer(rawPublic)
        rawCiphertext = AbdmCryptoService.ecdhEncrypt("raw-payload", rawPeerPrivate, rawPeerNonce, rawPublic, rawNonce)
        self.assertEqual(
            "raw-payload",
            AbdmCryptoService.ecdhDecrypt(rawCiphertext, rawPrivate, rawNonce, rawPeerPublic, rawPeerNonce),
        )

        fideliusPrivate, fideliusPublic, fideliusNonce = AbdmCryptoService.generateFideliusEcdhKeypair()
        peerPrivate, peerPublic, peerNonce = AbdmCryptoService.generateEcdhKeypairForPeer(fideliusPublic)
        fideliusCiphertext = AbdmCryptoService.ecdhEncrypt("fidelius-payload", peerPrivate, peerNonce, fideliusPublic, fideliusNonce)
        self.assertEqual(
            "fidelius-payload",
            AbdmCryptoService.ecdhDecrypt(fideliusCiphertext, fideliusPrivate, fideliusNonce, peerPublic, peerNonce),
        )

    def test_generated_fhir_bundle_is_structurally_valid(self) -> None:
        sys.path.insert(0, str(self.root))
        from modules.dataFlow.apiService import DataFlowApiService

        documentData = base64.b64encode(b"%PDF-1.4 test document").decode("utf-8")
        bundle = DataFlowApiService.buildFhirPayload(
            "hospital-a",
            "txn-123",
            {
                "careContextReference": "cc-123",
                "display": "Discharge summary",
                "patientId": "patient-123",
                "abhaAddress": "madhur@abdm",
                "abhaNumber": "12341234123412",
                "hipId": "IN0110000000",
                "hiTypes": ["HealthDocumentRecord"],
                "visitDate": "2026-07-09",
                "documentData": documentData,
                "documentTitle": "Health Document",
                "documentContentType": "application/pdf",
                "clinicalPayload": {
                    "patient": {"name": "Madhur Pathak", "gender": "male", "birthDate": "1990"},
                    "consultation": {
                        "practitioner_name": "Dr Test",
                        "practitioner_id": "HPR-1",
                        "organization_name": "Test Hospital",
                    },
                },
            },
        )
        entries = bundle["entry"]
        self.assertEqual("Bundle", bundle["resourceType"])
        self.assertEqual("document", bundle["type"])
        self.assertEqual("Composition", entries[0]["resource"]["resourceType"])
        composition = entries[0]["resource"]
        self.assertIn("custodian", composition)
        self.assertIn("encounter", composition)
        self.assertIn("author", composition)

        urls = {entry["fullUrl"] for entry in entries}
        referenced: set[str] = set()

        def collectReferences(value) -> None:
            if isinstance(value, dict):
                reference = value.get("reference")
                if isinstance(reference, str) and reference.startswith("urn:uuid:"):
                    referenced.add(reference)
                for child in value.values():
                    collectReferences(child)
            elif isinstance(value, list):
                for child in value:
                    collectReferences(child)

        collectReferences(bundle)
        self.assertEqual(set(), referenced - urls)
        resources = [entry["resource"] for entry in entries]
        self.assertTrue(any(resource["resourceType"] == "Patient" and resource.get("name") for resource in resources))
        self.assertTrue(any(resource["resourceType"] == "Practitioner" and resource.get("name") for resource in resources))
        self.assertTrue(any(resource["resourceType"] == "Organization" and resource.get("name") for resource in resources))
        self.assertTrue(any(resource["resourceType"] == "Encounter" and resource.get("status") == "finished" for resource in resources))
        documentReference = next(resource for resource in resources if resource["resourceType"] == "DocumentReference")
        attachment = documentReference["content"][0]["attachment"]
        base64.b64decode(attachment["data"], validate=True)

    def test_webhook_retry_contract(self) -> None:
        service = self.read("modules/webhookDispatcher/apiService.py")
        self.assertIn("response.status_code >= 500", service)
        self.assertIn("response.status_code >= 400", service)
        self.assertIn("retryable=True", service)
        self.assertIn("retryable=False", service)
        self.assertIn("batchItemFailures", service)

    def test_abha_lookup_contract(self) -> None:
        routes = self.read("modules/abha/routes.py")
        service = self.read("modules/abha/apiService.py")
        requests = self.read("modules/abha/requests.py")
        collection = self.read("Sahai_Production_Backend.postman_collection.json")
        self.assertIn('"/v1/abha/lookup"', routes)
        self.assertIn('"/v1/abha/lookup/verify"', routes)
        self.assertIn('auth["hospitalId"]', routes)
        self.assertIn("profile/login/request/otp", service)
        self.assertIn("profile/login/verify", service)
        self.assertIn("profile/login/verify/user", service)
        self.assertIn('"T-token": f"Bearer {tToken}"', service)
        self.assertIn('"X-token": f"Bearer {xToken}"', service)
        self.assertIn("accountSelectionRequired", service)
        self.assertIn("_saveLookupContext", service)
        self.assertIn("expiresAt", service)
        self.assertIn("Provide exactly one of 'mobile' or 'aadhaar'", requests)
        self.assertIn("03 - ABHA Lookup (Mobile/Aadhaar OTP Login)", collection)
        self.assertIn("09 - Optional: Direct Search & PHR Login", collection)
        self.assertIn("v1/abha/lookup/verify", collection)

    def test_abha_lookup_flow_returns_profile(self) -> None:
        import asyncio
        import base64 as b64
        import json as jsonlib

        sys.path.insert(0, str(self.root))
        from modules.abha.apiService import AbhaApiService
        from modules.abha.requests import AbhaLookupRequest, AbhaLookupVerifyRequest

        def makeJwt(payload: dict) -> str:
            def part(data: dict) -> str:
                return b64.urlsafe_b64encode(jsonlib.dumps(data).encode()).decode().rstrip("=")

            return f"{part({'alg': 'none'})}.{part(payload)}.sig"

        class FakeAbdmClient:
            def __init__(self, postResponses: dict, profile: dict) -> None:
                self.postResponses = postResponses
                self.profile = profile
                self.calls: list[tuple] = []

            async def fetchAbhaPublicKey(self) -> str:
                return "unused"

            async def abhaPost(self, path, payload, xToken="", extraHeaders=None):
                self.calls.append(("POST", path, payload, extraHeaders or {}))
                return self.postResponses[path]

            async def abhaGet(self, path, extraHeaders=None):
                self.calls.append(("GET", path, None, extraHeaders or {}))
                return self.profile

        class FakeDbService:
            def __init__(self) -> None:
                self.items: dict = {}

            def putItem(self, tableName, item, conditionExpression=None):
                self.items[(tableName, item["pk"], item["sk"])] = item

            def getItem(self, tableName, key, consistentRead=False):
                return self.items.get((tableName, key["pk"], key["sk"]))

            def deleteItem(self, tableName, key):
                self.items.pop((tableName, key["pk"], key["sk"]), None)

        async def fakeEncrypt(plainText: str) -> str:
            return f"enc({plainText})"

        profile = {"ABHANumber": "91-2345-6789-0123", "name": "Test Patient"}

        # Aadhaar path: verify returns a final (non-transfer) token, profile comes back in one call.
        transactionToken = makeJwt({"typ": "Transaction"})
        fakeClient = FakeAbdmClient(
            {
                "profile/login/request/otp": {"txnId": "txn-1", "message": "OTP sent"},
                "profile/login/verify": {"token": transactionToken},
            },
            profile,
        )
        service = AbhaApiService(abdmClient=fakeClient, dbService=FakeDbService())
        service._encrypt = fakeEncrypt
        started = asyncio.run(service.lookup("HOSP1", AbhaLookupRequest(aadhaar="123412341234")))
        self.assertEqual("txn-1", started["txnId"])
        result = asyncio.run(service.lookupVerify("HOSP1", AbhaLookupVerifyRequest(txnId="txn-1", otp="123456")))
        self.assertEqual(profile, result["profile"])
        self.assertEqual(transactionToken, result["xToken"])

        # Mobile path with a single linked account: transfer token is exchanged automatically.
        transferToken = makeJwt({"typ": "Transfer", "txnId": "txn-2"})
        fakeClient = FakeAbdmClient(
            {
                "profile/login/request/otp": {"txnId": "txn-2", "message": "OTP sent"},
                "profile/login/verify": {"token": transferToken, "accounts": [{"ABHANumber": "91234567890123"}]},
                "profile/login/verify/user": {"token": "final-x-token"},
            },
            profile,
        )
        service = AbhaApiService(abdmClient=fakeClient, dbService=FakeDbService())
        service._encrypt = fakeEncrypt
        asyncio.run(service.lookup("HOSP1", AbhaLookupRequest(mobile="9999999999")))
        result = asyncio.run(service.lookupVerify("HOSP1", AbhaLookupVerifyRequest(txnId="txn-2", otp="123456")))
        self.assertEqual("final-x-token", result["xToken"])
        self.assertEqual(profile, result["profile"])
        verifyUserCall = next(call for call in fakeClient.calls if call[1] == "profile/login/verify/user")
        self.assertEqual("91-2345-6789-0123", verifyUserCall[2]["ABHANumber"])
        self.assertEqual(f"Bearer {transferToken}", verifyUserCall[3]["T-token"])
        profileCall = next(call for call in fakeClient.calls if call[0] == "GET")
        self.assertEqual("Bearer final-x-token", profileCall[3]["X-token"])

        # Mobile path with multiple accounts: selection round-trip on the same endpoint, no second OTP.
        transferToken = makeJwt({"typ": "Transfer", "txnId": "txn-3"})
        fakeClient = FakeAbdmClient(
            {
                "profile/login/request/otp": {"txnId": "txn-3", "message": "OTP sent"},
                "profile/login/verify": {
                    "token": transferToken,
                    "accounts": [{"ABHANumber": "91234567890123"}, {"ABHANumber": "98765432109876"}],
                },
                "profile/login/verify/user": {"token": "final-x-token-2"},
            },
            profile,
        )
        fakeDb = FakeDbService()
        service = AbhaApiService(abdmClient=fakeClient, dbService=fakeDb)
        service._encrypt = fakeEncrypt
        asyncio.run(service.lookup("HOSP1", AbhaLookupRequest(mobile="9999999999")))
        first = asyncio.run(service.lookupVerify("HOSP1", AbhaLookupVerifyRequest(txnId="txn-3", otp="123456")))
        self.assertTrue(first["accountSelectionRequired"])
        self.assertEqual(2, len(first["accounts"]))
        second = asyncio.run(
            service.lookupVerify("HOSP1", AbhaLookupVerifyRequest(txnId="txn-3", abhaNumber="98765432109876"))
        )
        self.assertEqual("final-x-token-2", second["xToken"])
        self.assertEqual(profile, second["profile"])
        self.assertEqual({}, fakeDb.items)  # context cleaned up after completion

    def test_abdm_endpoints_are_not_hardcoded_in_application_code(self) -> None:
        forbidden = [
            "api/hiecm",
            "abdm.gov.in",
            "abhasbx",
            "healthidsbx",
        ]
        offenders: list[str] = []
        for folderName in ["common", "modules"]:
            for path in sorted((self.root / folderName).rglob("*.py")):
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in text:
                        offenders.append(f"{path.relative_to(self.root)} contains {token}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
