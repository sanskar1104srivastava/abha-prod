# Production Backend — ABDM Gateway Architecture

> **Status: Implemented.** This document was originally a planning spec. The sections below
> reflect the actual deployed architecture as of M2 completion.

## What Is Built

The production-backend is a stateful ABDM bridge. It stores request metadata (not clinical data) for correlation and tracking, and delivers callbacks to hospitals through two independent channels.

### Inbound Callback Chain (ABDM → Hospital)

```
ABDM
  → callbackRouter Lambda
      ├── extracts correlation IDs (requestId, transactionId, consentId, hipId)
      ├── stores raw callback + matched request to DynamoDB (sahaiCallbacks, sahaiRequestLog)
      ├── enqueues {abdm_path, raw_body, hospital_id} → sahaiAbdmCallbacksQueue SQS
      └── enqueues formatted Sahai event → sahaiWebhookEventsQueue SQS

  → abdmCallbackConsumer Lambda (sahaiAbdmCallbacksQueue trigger)
      ├── resolves hospitalId: (1) SQS hint, (2) correlationId DB lookup, (3) hipId GSI fallback
      └── POSTs raw ABDM body to hospital webhookUrl
          Headers: X-Abdm-Path, X-Abdm-Signature (HMAC-SHA256)

  → webhookDispatcher Lambda (sahaiWebhookEventsQueue trigger)
      └── POSTs formatted Sahai event to hospital webhookUrl
          Headers: X-Sahai-Event-Id, X-Sahai-Event-Type, X-Sahai-Signature
```

Each ABDM callback produces **two** deliveries to the hospital webhook. Only matched callbacks (correlated to a tracked outbound request) produce the formatted Sahai event.

### Outbound Request Chain (Hospital → ABDM)

```
Hospital
  → POST /v1/{flow} → externalApi Lambda
      ├── validates request (Pydantic strict model)
      ├── generates trackingId + requestId
      ├── stores request metadata to sahaiRequestLog (routing IDs + status only)
      ├── forwards to ABDM
      └── returns {trackingId, requestId, status: "accepted"} to hospital
```

### Storage (What Is Stored)

| Store | Content |
|---|---|
| `sahaiRequestLog` | trackingId, requestId, transactionId, consentId, hospitalId, status, TTL 30d |
| `sahaiCallbacks` | raw ABDM callback body + correlation IDs, for audit |
| `sahaiCareContexts` | care context metadata: reference, display, hiTypes, clinicalPayload (no full clinical FHIR) |
| `sahaiAbdmCorrelation` | requestId/transactionId/consentId → hospitalId mapping |
| `sahaiHealthRecords` | encrypted inbound health data (HIU flow only) |
| S3 `sahai-production-callback-bodies` | raw ABDM callback bodies for audit (not health records) |

Patient clinical data is **not stored** in the bridge layer. `clinicalPayload` in `sahaiCareContexts` is whatever the hospital sends at care context creation time; it is used only when the data-flow worker builds a FHIR bundle for the HIP data push.

---

## Original Plan Notes (Kept for Reference)

---

## Storage Policy — What Is Allowed

| Store | Allowed Content | Not Allowed |
|---|---|---|
| `abdm_audit_log` | request_id, abdm_path, hospital_id, direction, status, TTL 90d | Any body content, patient data |
| `hospital_registry` | hospital_id, webhook_url, hmac_secret | Patient data |
| `abdmCorrelation` (new) | requestId / transactionId / consentId → hospitalId, TTL 30d | Full request payload, clinical data |

Everything else: **forward and discard**.

---

## Flow

### Inbound: ABDM → Hospital

```
ABDM
  → abha-callback Lambda (ZIP)
      writes audit row to abdm_audit_log (metadata only)
      puts {abdm_path, raw_body, hospital_id} to abdm-callbacks SQS
      returns 202 immediately

  → abdmCallbackConsumer Lambda (SQS trigger)
      1. Parse abdm_path + raw_body from SQS message
      2. Extract requestId / transactionId / consentId from body
      3. Look up hospitalId from abdmCorrelation table
         (if hospital_id already in SQS message from URL path, use that directly)
      4. Fetch webhook_url + hmac_secret from hospital_registry table
      5. POST raw_body as-is to hospital webhook with X-Abdm-Signature HMAC header
      6. Update abdm_audit_log status to "forwarded" or "forward_failed"
```

### Outbound: Hospital → ABDM

```
Hospital
  → POST /v1/{flow} → externalApi Lambda
      1. Validate request
      2. Generate requestId (UUID)
      3. Write ONLY (requestId → hospitalId) to abdmCorrelation table — no payload stored
      4. Forward to ABDM with generated requestId
      5. Return trackingId to hospital
```

---

## Changes Required Inside production-backend

### 1. NEW `modules/abdmCallbackConsumer/correlationService.py`

Thin DynamoDB read-only service.

- Table: `abdmCorrelation` (PK: `pk` = `"req#<requestId>"`, or `"txn#<transactionId>"`)
- Method: `findHospitalId(requestId, transactionId, consentId) → str | None`
  - Try each correlation key in order, return first match
- No writes (writes happen in externalApi when outbound request is made)

### 2. NEW `modules/abdmCallbackConsumer/forwarderService.py`

Forwards raw ABDM payload to hospital webhook.

- Reads `webhook_url` and `hmac_secret` from `hospital_registry` DynamoDB table
  (PK: `"hosp#<hospital_id>"`)
- Computes HMAC-SHA256 of raw body using hmac_secret
- POST to webhook_url with headers:
  - `Content-Type: application/json`
  - `X-Abdm-Signature: <hmac>`
  - `X-Abdm-Path: <abdm_path>`
- Returns (success: bool, status_code: int)
- On 5xx or timeout: retryable (return failure so SQS retries)
- On 4xx: non-retryable (log and discard)

### 3. REWRITE `modules/abdmCallbackConsumer/sqsMain.py`

**Current (wrong)**: calls `callbackRouter.handleCallback` which has data storage side effects.

**New**: direct forwarding pipeline using only the two new services above.

```python
def handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["body"])
        abdm_path  = message["abdm_path"]
        raw_body   = message["raw_body"]
        hospital_id = message.get("hospital_id") or ""

        payload = json.loads(raw_body)

        # Step 1: resolve hospital_id
        if not hospital_id:
            hospital_id = correlationService.findHospitalId(
                payload.get("requestId") or payload.get("resp", {}).get("requestId"),
                payload.get("transactionId"),
                payload.get("consentId"),
            )

        if not hospital_id:
            # unroutable — log and discard (no retry)
            continue

        # Step 2: forward raw body to hospital
        ok = forwarderService.forward(hospital_id, abdm_path, raw_body)

        # Step 3: mark retryable failures
        if not ok:
            failures.append({"itemIdentifier": record["messageId"]})
```

### 4. MODIFY `modules/externalApi/apiService.py`

**Current `_acceptAndLog`**: stores full request payload (clinical data, key material, consent
details, care contexts) in `sahaiRequestLog`.

**Required change**: after accepting the request, write ONLY the correlation IDs to
`abdmCorrelation` table. Do NOT write to `sahaiRequestLog` at all (or limit it to routing IDs).

Specifically, after generating `requestId` for each outbound call, write:

```python
# for each outbound flow (requestConsent, requestHealthInformation, etc.)
correlationService.store(requestId=requestId, hospitalId=hospitalId)
# for flows that produce a transactionId:
correlationService.store(transactionId=transactionId, hospitalId=hospitalId)
# for flows using consentId:
correlationService.store(consentId=consentId, hospitalId=hospitalId)
```

This replaces the full `sahaiRequestLog` write.

### 5. NEW `modules/abdmCallbackConsumer/abdmCorrelationDbService.py`

Handles both reads (for inbound routing) and writes (called from externalApi outbound flows).

DynamoDB table: `abdmCorrelation`
- PK: `pk` (string) — values like `"req#<uuid>"`, `"txn#<uuid>"`, `"cid#<uuid>"`
- Attributes: `hospitalId`, `ttl` (epoch, 30 days)
- GSI not needed — PK lookup is direct

Methods:
- `storeRequestId(requestId, hospitalId)` → write `pk="req#<requestId>"`
- `storeTransactionId(transactionId, hospitalId)` → write `pk="txn#<transactionId>"`
- `storeConsentId(consentId, hospitalId)` → write `pk="cid#<consentId>"`
- `findHospitalId(requestId, transactionId, consentId) → str | None`
  — tries each key in order, returns first match

### 6. UPDATE `deploy/provision.sh`

Add `abdmCorrelation` DynamoDB table creation (PAY_PER_REQUEST, TTL on `ttl` attribute).

---

## What NOT To Use (Existing Modules — Not In Gateway Path)

| Module | Why Excluded |
|---|---|
| `callbackRouter` | Stores full raw callback body; sends transformed payload not raw ABDM body |
| `webhookDispatcher` | Sends a custom envelope not the raw ABDM body; reads/deletes from S3 health data |
| `dataFlow` | Decrypts and stores FHIR health records — entirely incompatible with gateway |

These modules remain in the codebase (M1/existing flows may use them) but the gateway path
does **not** go through them.

---

## Files To Create / Modify

| File | Action |
|---|---|
| `modules/abdmCallbackConsumer/abdmCorrelationDbService.py` | CREATE |
| `modules/abdmCallbackConsumer/correlationService.py` | CREATE |
| `modules/abdmCallbackConsumer/forwarderService.py` | CREATE |
| `modules/abdmCallbackConsumer/sqsMain.py` | REWRITE |
| `modules/externalApi/apiService.py` | MODIFY — write to abdmCorrelation instead of sahaiRequestLog |
| `deploy/provision.sh` | MODIFY — add abdmCorrelation table |

---

## Files Not To Touch

- `callback/lambda_function.py` — correct as-is (audit + SQS)
- `modules/callbackRouter/` — leave as-is, not in gateway path
- `modules/webhookDispatcher/` — leave as-is, not in gateway path
- `modules/dataFlow/` — leave as-is, not in gateway path
- `backend/` — M1 flows, untouched
- `abha-callback-api` — base URL unchanged
