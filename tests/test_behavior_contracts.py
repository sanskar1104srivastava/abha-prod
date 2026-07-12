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
        self.assertIn("enqueueHealthInformationRequestsForConsentArtefacts", service)
        self.assertIn("HIU_HEALTH_INFORMATION_REQUEST", service)
        self.assertIn("buildConsentStatusPayload", service)
        self.assertIn('"patientReference"', service)
        self.assertIn('"consentArtefacts"', service)
        self.assertIn('"response": {"requestId": requestBody.requestId}', hip)
        self.assertIn('correlationIds.get("requestId") or callbackId', service)
        self.assertIn("class CallbackAckResponse", response)
        self.assertNotIn("correlationStatus", response)
        self.assertNotIn("trackingId", response)

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

    def test_data_flow_encrypt_decrypt_contract(self) -> None:
        service = self.read("modules/dataFlow/apiService.py")
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
