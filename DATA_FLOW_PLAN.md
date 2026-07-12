# Health Data Delivery Plan

## What happens

1. ABDM/HIP pushes encrypted FHIR bundle to `POST /data`
2. `dataFlow` Lambda saves the encrypted blob to S3 as-is — no decryption
3. `dataFlow` Lambda puts a thin message on `sahaiDataFlowJobsQueue` (just IDs, not the data)
4. `webhookDispatcher` Lambda picks up the message, reads the encrypted blob from S3, POSTs it to the hospital's registered webhook URL
5. On successful delivery (HTTP 2xx from hospital) → delete from S3

Data never leaves encrypted. Hospital decrypts using the key material they received during the health-information request flow.

---

## SQS message (thin — stays under 256KB)

```json
{
  "jobId": "evt_...",
  "jobType": "HIP_HEALTH_INFORMATION_REQUEST",
  "hospitalId": "HOSP-...",
  "trackingId": "trk_...",
  "s3Key": "data/2026/06/24/evt_....json",
  "hipId": "IN...",
  "correlationIds": { "transactionId": "...", "consentId": "..." }
}
```

---

## Webhook POST to hospital (what the hospital receives)

```json
{
  "eventId": "evt_...",
  "eventType": "HEALTH_RECORDS_RECEIVED",
  "trackingId": "trk_...",
  "hipId": "IN...",
  "encryptedData": { ...raw encrypted FHIR payload from ABDM... }
}
```

Signed with `X-Sahai-Signature` header (same HMAC-SHA256 as all other webhook events).

Hospital does **not** decrypt the data themselves. They pass the `encryptedData` + `trackingId`
to our decryption endpoint and receive plain FHIR records back.

---

## Decryption endpoint (called by hospital after receiving webhook)

```
POST /v1/health-records/{trackingId}/decrypt
Authorization: Bearer <apiKey>
Body: { "encryptedData": { ...raw encrypted payload... } }
```

`dataFlow` Lambda:
- Loads the `keySession` (ECDH private key + nonce) stored in `sahaiRequestLog` during the original health-information request
- Decrypts the FHIR bundle
- Returns plain FHIR records to the hospital

Hospital never handles ABDM crypto — we abstract it entirely.

---

## S3 lifecycle

| Step | Action |
|---|---|
| Data arrives | Save to `sahai-production-encrypted-records/{s3Key}` |
| Delivery succeeds | Delete from S3 |
| Delivery fails (< 3 retries) | SQS retries automatically |
| All retries exhausted | Message goes to `sahaiDataFlowJobsDlq` — S3 object stays for manual inspection |

---

---

## What is already built

### `dataFlow` Lambda (`modules/dataFlow/apiService.py`)
- ✅ Receives ABDM inbound data push at `POST /data`
- ✅ Correlates to `hospitalId` / `trackingId` via `transactionId` / `consentId` GSI lookup on `sahaiRequestLog`
- ✅ Saves full encrypted payload to S3 (`sahai-production-encrypted-records/inbound-data/{date}/{dataFlowId}.json`)
- ✅ Stores metadata in `sahaiHealthRecords` DynamoDB with `encryptedS3Key`
- ✅ Decrypts entries immediately using the ECDH `keySession` stored in `sahaiRequestLog` during the health-information request
- ✅ Saves decrypted records to S3 (`sahai-production-decrypted-records/decrypted-data/{date}/{recordId}.json`)
- ✅ Stores decrypted metadata in `sahaiHealthRecords` DynamoDB with `decryptedS3Key`
- ✅ Returns 202 to ABDM

### `webhookDispatcher` Lambda (`modules/webhookDispatcher/apiService.py`)
- ✅ Reads SQS events and POSTs to hospital webhook URL
- ✅ Looks up hospital webhook URL and secret from `sahaiHospitalTenants`
- ✅ Signs every delivery with HMAC-SHA256 (`X-Sahai-Signature`)
- ✅ Retry logic via SQS `batchItemFailures` (up to 3x, then DLQ)
- ✅ Marks delivery result in `sahaiWebhookEvents` DynamoDB

### Infrastructure
- ✅ `sahai-production-encrypted-records` S3 bucket exists
- ✅ `sahai-production-decrypted-records` S3 bucket exists
- ✅ `sahaiDataFlowJobsQueue` + `sahaiDataFlowJobsDlq` SQS queues exist
- ✅ `sahaiWebhookEventsQueue` + `sahaiWebhookEventsDlq` SQS queues exist
- ✅ `WebhookSignatureService` signing implemented
- ✅ `sahaiRequestLog` GSIs for correlation (transactionId, consentId, hipId)

---

## What is missing (needs to be built)

### 1. `dataFlow` Lambda — enqueue webhook event after data arrives

Currently `handleInboundDataPush` saves to S3 and decrypts but **never notifies the hospital**.

Need to add at the end of `handleInboundDataPush` (when `matchedRequest` is found):
- Put a thin message on `sahaiWebhookEventsQueue` with:
  ```json
  {
    "eventId": "evt_...",
    "eventType": "HEALTH_RECORDS_RECEIVED",
    "hospitalId": "HOSP-...",
    "trackingId": "trk_...",
    "encryptedS3Key": "inbound-data/2026/06/24/evt_....json"
  }
  ```
- The encrypted entries are **not** in the SQS message (too large) — only the S3 key

### 2. `webhookDispatcher` Lambda — read S3 and include encrypted data in POST

Currently `buildWebhookBody` only sends the thin event fields.

Need to add:
- When `eventType == "HEALTH_RECORDS_RECEIVED"` and `encryptedS3Key` is present:
  - Read the encrypted blob from S3 by `encryptedS3Key`
  - Include the `entries` array from the blob in the webhook POST body as `encryptedData`
- Hospital receives:
  ```json
  {
    "eventType": "HEALTH_RECORDS_RECEIVED",
    "trackingId": "trk_...",
    "encryptedData": [ { "content": "...", "media": "...", "careContextReference": "..." } ]
  }
  ```

### 3. Decryption endpoint — `POST /v1/health-records/{trackingId}/decrypt`

Hospital sends back the encrypted entries, we return already-decrypted FHIR from the S3 key we saved.

- Look up `sahaiHealthRecords` by `trackingId` to get `decryptedS3Key`
- Read decrypted FHIR from `sahai-production-decrypted-records` by that key
- Return plain FHIR to hospital
- No re-decryption needed — decryption already happened on inbound (step 1 above)
