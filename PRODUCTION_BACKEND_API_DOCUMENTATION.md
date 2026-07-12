# Sahai Production Backend API Documentation

This document describes the deployed `production-backend` API surface from the source code in this folder.

Base URL:

```text
https://4sdj5gmx8g.execute-api.ap-south-1.amazonaws.com
```

Use only real values from your hospital account, ABDM callbacks, or previous API responses. The angle-bracket values in this document are placeholders and each one is defined in the field tables.

## Recommended End-to-End Order

1. Operator creates the hospital customer with `POST /v1/admin/customers`.
2. Hospital stores the returned `<apiKey>`.
3. Hospital verifies access with `GET /v1/auth/me`.
4. Hospital configures webhooks with `PUT /v1/webhook-endpoint`.
5. Hospital tests webhooks with `POST /v1/webhook-endpoint/test`.
6. For ABHA account work, use the ABHA enrollment, lookup, or PHR APIs.
7. For HIP care-context linking, request/fetch link token, link care contexts, then notify ABDM.
8. For HIU consent, request consent, wait for consent webhook, fetch artefact if needed, then request health information.
9. Poll async work using `GET /v1/status/<trackingId>` until the status is terminal.
10. Fetch received/decrypted records using `/v1/health-records/<trackingId>` and `/v1/health-records/<trackingId>/decrypt`.

## Common Rules

### Authentication

Customer APIs require:

```http
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Admin/operator APIs require:

```http
Authorization: Bearer <adminKey>
Content-Type: application/json
```

### Idempotency

The following async APIs also require:

```http
Idempotency-Key: <idempotencyKey>
```

Use one unique key per business operation. If the same key is reused with the same body, the stored response is returned. If the same key is reused with a different body, the API returns `409 IDEMPOTENCY_CONFLICT`.

Idempotent APIs:

| API | Purpose |
|---|---|
| `POST /v1/link-token` | Request ABDM link token |
| `POST /v1/care-contexts/link` | Link care contexts |
| `POST /v1/consents` | Create HIU consent request |
| `POST /v1/health-information` | Request health information |

### Rate Limits

No application-level rate limit is defined in the `production-backend` source code. Requests may still be limited by API Gateway, Lambda concurrency, AWS account limits, or ABDM upstream throttling. Until an explicit quota is configured, clients should use conservative polling:

| Operation | Recommended client behavior |
|---|---|
| `GET /v1/status/<trackingId>` | Poll every 3 to 5 seconds for the first minute, then back off to 15 to 30 seconds. |
| ABDM OTP flows | Do not spam OTP endpoints. Wait for the ABDM response/callback before retrying. |
| Async POST APIs | Use one idempotency key per operation and retry only on network failure or documented retryable server errors. |

### Standard Error Response

All application errors use this shape:

```json
{
  "errorCode": "<errorCode>",
  "message": "<message>",
  "details": {}
}
```

| Field | Definition |
|---|---|
| `errorCode` | Stable machine-readable error code. |
| `message` | Human-readable explanation. |
| `details` | Extra structured details, if available. |

Common error codes:

| HTTP | errorCode | Meaning |
|---:|---|---|
| 400 | `INVALID_REQUEST` | Request is structurally wrong or contains a forbidden client-supplied value. |
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | Required `Idempotency-Key` header is missing. |
| 401 | `NOT_AUTHENTICATED` | API key/admin key is missing, invalid, or inactive. |
| 403 | `FORBIDDEN` | Authenticated key is not allowed for this operation. |
| 404 | `INVALID_REQUEST` | Requested tracking ID or decrypted result was not found. |
| 409 | `IDEMPOTENCY_CONFLICT` | Same idempotency key was already used with a different body. |
| 422 | FastAPI validation error | Required field is missing, wrong type, too short/long, or an extra field was sent to a strict request model. |
| 424 | `UPSTREAM_ERROR` | ABDM or another upstream service rejected or failed the request. |
| 500 | `INTERNAL_ERROR` | Backend failed unexpectedly. |
| 503 | `INTERNAL_ERROR` | Required backend configuration is missing. |

### ABDM Pass-Through Responses

Several endpoints return the raw ABDM gateway or ABHA response without reshaping it. For those endpoints, this document defines the Sahai request contract, auth, validation, and backend behavior. The success body is controlled by the ABDM API version configured in backend secrets.

| Sahai endpoint group | Backend ABDM operation |
|---|---|
| `/v1/abha/enroll/*` | ABDM ABHA enrollment APIs. |
| `/v1/abha/address/*` | ABDM ABHA address suggestion/set APIs. |
| `/v1/abha/lookup/*` | ABDM ABHA profile login APIs. |
| `/v1/abha/search/*` | ABDM ABHA profile search APIs. |
| `/v1/abha/phr/*` | ABDM PHR login/search APIs. |
| `/v1/hip/link/fetch-modes` | ABDM HIP auth modes API, endpoint key `hipFetchModes`. |
| `/v1/hip/link/otp-init` | ABDM HIP auth init API, endpoint key `hipOtpInit`. |
| `/v1/hip/link/otp-confirm` | ABDM HIP auth confirm API, endpoint key `hipOtpConfirm`. |
| `/v1/hip/link/care-context/notify` | ABDM HIP care-context notify API, endpoint key `hipContextNotify`. |
| `/v1/hip/sms-notify` | ABDM HIP SMS notify API, endpoint key `hipSmsNotify`. |
| `/v1/hip/consent/on-notify` | ABDM HIP consent acknowledgement API, endpoint key `consentHipOnNotify`. |
| `/v1/hip/health-information/on-request` | ABDM HIP health-information acknowledgement API, endpoint key `healthInformationHipOnRequest`. |
| `/v1/consents/status` | ABDM HIU consent status API, endpoint key `consentStatus`. |
| `/v1/consents/fetch` | ABDM HIU consent fetch API, endpoint key `consentFetch`. |
| `/v1/share/on-share` | ABDM patient scan-and-share acknowledgement API, endpoint key `patientOnShare`. |

When integrating, keep the ABDM specification for the configured environment beside this document. If ABDM changes a response field, the Sahai pass-through endpoint can return that changed field without a Sahai code change.

## Value Definitions

| Placeholder | Definition |
|---|---|
| `<baseUrl>` | `https://4sdj5gmx8g.execute-api.ap-south-1.amazonaws.com` for the current sandbox environment file. |
| `<adminKey>` | Operator/admin bearer key configured in backend secrets. Used only for `/v1/admin/*` and `/v1/auth/register`. |
| `<apiKey>` | Hospital customer API key returned when a customer is created or rotated. |
| `<hospitalId>` | Backend-generated hospital tenant ID returned during customer creation. |
| `<loginId>` | Unique hospital login identifier. Usually the hospital email or customer slug. |
| `<password>` | Hospital login password. Minimum 8 characters for account creation. |
| `<hospitalName>` | Display name of the hospital/customer. |
| `<hipId>` | ABDM HIP ID assigned to the hospital/facility. |
| `<hiuId>` | ABDM HIU ID assigned to the hospital/facility. |
| `<webhookUrl>` | HTTPS endpoint where Sahai sends customer-facing webhook events. |
| `<webhookSecret>` | Customer secret used to verify HMAC-SHA256 webhook signatures. Minimum 16 characters. |
| `<callbackUrl>` | Backend callback URL registered with ABDM gateway. |
| `<facilityId>` | ABDM facility/provider ID used for bridge registration. Defaults to `hipId` when omitted in auto setup. |
| `<facilityName>` | Facility display name used for bridge registration. Defaults to `hospitalName` when omitted in auto setup. |
| `<idempotencyKey>` | Unique key generated by client for one async request. |
| `<trackingId>` | Backend tracking ID returned by async APIs. Use it to poll `/v1/status/{trackingId}`. |
| `<requestId>` | ABDM request ID from Sahai response, ABDM callback, or generated gateway request. |
| `<txnId>` | ABDM transaction ID returned by OTP/session APIs. |
| `<xToken>` | ABDM profile token returned by lookup/verify flows. Used to fetch profile, card, or QR. |
| `<phrToken>` | PHR login token returned by PHR verify OTP flow, when ABDM returns it. |
| `<abhaAddress>` | Patient ABHA address. |
| `<abhaNumber>` | Patient ABHA number. Hyphens are accepted where noted and removed before ABDM dispatch. |
| `<aadhaar>` | Patient 12-digit Aadhaar number. |
| `<mobile>` | Patient 10-digit mobile number without country code unless the API says otherwise. |
| `<phoneNo>` | Patient mobile number with country code for deep-link SMS. |
| `<otp>` | OTP entered by the patient. |
| `<patientReference>` | Hospital-side patient reference number. |
| `<patientDisplay>` | Human-readable patient label shown during ABDM linking. |
| `<careContextReference>` | Hospital-side care context reference number. |
| `<linkToken>` | ABDM link token received through the linking flow/callback. |
| `<consentRequestId>` | ABDM consent request ID. In this backend it is the same generated value as the request ID for `POST /v1/consents`. |
| `<consentId>` | ABDM consent artefact ID from a granted consent callback. |
| `<transactionId>` | ABDM health-information or link transaction ID. |
| `<dataPushUrl>` | HTTPS URL where HIP should push encrypted health information. Optional when backend `selfDataEndpointUrl` is configured. |
| `<environment>` | Customer environment stored for the hospital account, for example sandbox or production depending on backend provisioning. |
| `<bridgeSetupStatus>` | Result of automatic bridge setup, such as completed, skipped, failed, or partial according to backend/ABDM outcome. |
| `<webhookStatusCode>` | HTTP status returned by the customer's webhook endpoint during test delivery. |
| `<abdmGatewaySessionUrl>` | ABDM gateway session-token endpoint resolved from backend configuration. |
| `<abdmClientId>` | ABDM client ID configured in backend secrets. |
| `<cmId>` | ABDM consent manager ID configured in backend secrets. |
| `<timestamp>` | ISO 8601 timestamp generated by the backend for outbound ABDM calls. |
| `<abdmResponseBody>` | Response body returned by ABDM during a diagnostic call. |
| `<upstreamStatusCode>` | HTTP status returned by ABDM or another upstream service. |
| `<abdmGatewayToken>` | Valid ABDM gateway bearer token. |
| `<newApiKey>` | Newly generated hospital API key returned by key rotation. |
| `<createdAt>` | ISO 8601 timestamp when the hospital account was created. |
| `<updatedAt>` | ISO 8601 timestamp when the hospital account was last updated, or null if it has not been updated. |
| `<loginIdValue>` | Patient identifier value used for ABHA lookup; its meaning depends on `loginHint`. |
| `<otpSystem>` | ABDM OTP system name, usually `abdm` or `aadhaar`. |
| `<patientName>` | Patient name used for ABDM demographic matching. |
| `<gender>` | Patient gender value expected by ABDM for demographic matching. |
| `<yearOfBirth>` | Patient birth year between 1900 and 2100. |
| `<eventType>` | Backend event type stored against the tracked request. |
| `<careContextDisplay>` | Human-readable label for a care context. |
| `<hiType>` | ABDM health information type for a record, consent, or care context. |
| `<documentData>` | Document payload stored with the care context when a document is available. |
| `<documentTitle>` | Human-readable document title. |
| `<documentContentType>` | MIME type of `documentData`. |
| `<purposeText>` | Human-readable ABDM consent purpose. |
| `<purposeCode>` | ABDM consent purpose code. |
| `<purposeRefUri>` | ABDM purpose reference URI. |
| `<requesterName>` | Name of the consent requester. |
| `<requesterIdentifierType>` | Identifier type for the requester. |
| `<requesterIdentifierValue>` | Identifier value for the requester. |
| `<requesterIdentifierSystem>` | Identifier system for the requester. |
| `<fromTimestamp>` | ISO 8601 start timestamp for consent or health-information date range. |
| `<toTimestamp>` | ISO 8601 end timestamp for consent or health-information date range. |
| `<dataEraseAtTimestamp>` | ISO 8601 timestamp after which received data must be erased. |
| `<entryCount>` | Number of decrypted entries returned for a tracking ID. |
| `<mediaType>` | MIME type of a returned/decrypted record. |
| `<tokenNumber>` | Hospital token or queue number issued to the patient. |
| `<expiryTimestamp>` | ISO 8601 expiry timestamp for the hospital token. |
| `<eventId>` | Unique Sahai webhook/data-flow event ID. |
| `<signature>` | `sha256=<lowercaseHexDigest>` HMAC signature of the raw webhook body. |
| `<callbackId>` | Internal Sahai callback ID created when ABDM callback is received. |
| `<callbackPath>` | ABDM callback path received by Sahai. |
| `<dataFlowId>` | Sahai ID for an inbound or outbound health-information data-flow operation. |
| `<encryptedS3Key>` | Internal S3 object key for encrypted payload storage. |
| `<receivedAt>` | ISO 8601 timestamp when a callback or data push was received. |
| `<careContextCount>` | Number of care contexts included in a user-linking discovery response. |
| `<linkReferenceNumber>` | Hospital-generated link or OTP reference for user-initiated linking. |
| `<communicationHint>` | Masked communication destination or short instruction shown to the patient. |
| `<communicationExpiryTimestamp>` | ISO 8601 timestamp when the link/authentication step expires. |

## Webhook Contract

### Dual Delivery

Each ABDM callback arrives at the hospital webhook **twice** through two independent channels.

**Delivery 1 — Raw ABDM body (from `abdmCallbackConsumer`):**

```http
POST <webhookUrl>
Content-Type: application/json
X-Abdm-Path: <abdmCallbackPath>
X-Abdm-Signature: <hmacSha256OfRawBody>
<raw ABDM callback body>
```

This is the exact body ABDM sent. The signature is HMAC-SHA256 of the raw body using the hospital `webhookSecret`. Use `X-Abdm-Path` to identify the ABDM callback type (e.g. `/api/v3/link/on_carecontext`, `/api/v3/consent/request/hip/notify`).

**Delivery 2 — Formatted Sahai event (from `webhookEventsQueue`):**

Sahai extracts correlation IDs, matches the request to a tracking ID, classifies the event type, and sends a thinner structured envelope. This is the primary delivery for polling and business logic. Described in full below.

Only matched callbacks (those correlated to a tracked request) produce a formatted Sahai event. Unmatched callbacks (e.g. ABDM-initiated events with no prior outbound request) may only produce the raw delivery.

---

Sahai sends customer-facing webhook events to the `webhookUrl` configured by `PUT /v1/webhook-endpoint`. The webhook body is not the full raw ABDM callback. The callback router stores the raw callback internally, extracts correlation IDs, then dispatches a thinner event body to the hospital webhook.

### Webhook Headers

```http
Content-Type: application/json
X-Sahai-Event-Id: <eventId>
X-Sahai-Event-Type: <eventType>
X-Sahai-Signature: <signature>
```

| Header | Definition |
|---|---|
| `X-Sahai-Event-Id` | Unique webhook event ID generated by Sahai. |
| `X-Sahai-Event-Type` | Event type. See event table below. |
| `X-Sahai-Signature` | HMAC-SHA256 signature of the exact raw request body using the hospital `webhookSecret`, formatted as `sha256=<lowercaseHexDigest>`. |

Signature verification:

1. Read the raw HTTP request body exactly as received.
2. Compute `HMAC-SHA256(rawBody, webhookSecret)`.
3. Prefix the lowercase hex digest with `sha256=`.
4. Compare that full value with `X-Sahai-Signature` using a constant-time comparison.
5. Reject the webhook if the signature does not match.

### Webhook Body

```json
{
  "eventId": "<eventId>",
  "eventType": "<eventType>",
  "trackingId": "<trackingId>",
  "callbackId": "<callbackId>",
  "callbackPath": "<callbackPath>",
  "correlationIds": {
    "requestId": "<requestId>",
    "transactionId": "<transactionId>",
    "consentRequestId": "<consentRequestId>",
    "consentId": "<consentId>",
    "hipId": "<hipId>",
    "hiuId": "<hiuId>",
    "hasKeyMaterial": "true"
  },
  "payload": {},
  "encryptedData": []
}
```

| Field | Definition |
|---|---|
| `eventId` | Unique webhook event ID. Same as `X-Sahai-Event-Id`. |
| `eventType` | Sahai event type. Same as `X-Sahai-Event-Type`. |
| `trackingId` | Tracking ID of the original Sahai async request when the callback can be correlated. |
| `callbackId` | Internal callback ID assigned by Sahai. Useful for support/debugging. |
| `callbackPath` | ABDM callback path received by Sahai. |
| `correlationIds` | IDs extracted from the callback and used to match it with a tracked request. Empty values are removed before delivery. |
| `payload` | Thin callback payload. Only important ABDM keys are forwarded: `requestId`, `transactionId`, `consentRequestId`, `consentId`, `response`, `resp`, `error`, `notification`, and `hiRequest`. |
| `encryptedData` | Present only for `healthInformation.received` when encrypted entries are available from storage. Contains the encrypted ABDM data entries from the inbound data push. |

### Webhook Event Types

| eventType | When it is sent | Terminal for polling |
|---|---|---:|
| `callback.received` | A matched ABDM callback was received but did not map to a more specific event type. | Depends on the flow; inspect `payload`. |
| `consent.granted` | Consent callback contains `notification.status = GRANTED`. | Yes for consent approval; health data is not pulled until a health-information request is made. |
| `consent.denied` | Consent callback contains `notification.status = DENIED`, `REVOKED`, or `EXPIRED`. | Yes. |
| `dataFlow.jobCreated` | ABDM sent a HIP health-information request and Sahai queued a data-flow job. | No. Wait for `healthInformation.pushed` or `failed`. |
| `healthInformation.received` | Sahai received encrypted health data through `/data`, stored it, and attempted decryption. | Yes when status is `decrypted`; otherwise inspect errors. |
| `healthInformation.pushed` | Sahai pushed HIP health information to the requester. | Yes. |

### Webhook Delivery and Retries

The dispatcher treats webhook responses as follows:

| Customer webhook result | Sahai delivery status | Retry |
|---|---|---:|
| HTTP 2xx or 3xx | `delivered` | No |
| HTTP 4xx | `nonRetryableFailed` | No |
| HTTP 5xx | `retryableFailed` | Yes |
| Network error, connection error, or timeout | `retryableFailed` | Yes |
| Missing webhook URL or secret | `configMissing` | No |

## Flow 1: Operator Setup

### 1. Health Check

```http
GET <baseUrl>/v1/health
```

Headers: none required.

Success response:

```json
{
  "status": "ok",
  "service": "sahai-production-external-api"
}
```

### 2. Create Hospital Customer

```http
POST <baseUrl>/v1/admin/customers
Authorization: Bearer <adminKey>
Content-Type: application/json
```

Request body:

```json
{
  "loginId": "<loginId>",
  "password": "<password>",
  "hospitalName": "<hospitalName>",
  "hipId": "<hipId>",
  "hiuId": "<hiuId>",
  "webhookUrl": "<webhookUrl>",
  "webhookSecret": "<webhookSecret>",
  "dataPushUrl": "<dataPushUrl>",
  "setupBridge": true,
  "facilityId": "<facilityId>",
  "facilityName": "<facilityName>",
  "hrp": []
}
```

Field definitions:

| Field | Required | Definition |
|---|---:|---|
| `loginId` | Yes | Unique hospital login identifier. |
| `password` | Yes | Password for login. Minimum 8 characters. |
| `hospitalName` | Yes | Hospital display name. |
| `hipId` | Yes | ABDM HIP ID for this hospital. |
| `hiuId` | Yes | ABDM HIU ID for this hospital. |
| `webhookUrl` | No | HTTPS customer webhook endpoint. |
| `webhookSecret` | No | Secret used to sign webhooks for this customer. |
| `dataPushUrl` | No | HTTPS endpoint where the HIP pushes encrypted health information directly to this hospital. Can also be set later with `PUT /v1/data-push-endpoint`. |
| `setupBridge` | No | When `true`, backend registers callback URL and bridge services after account creation. Defaults to `true`. |
| `facilityId` | No | Facility/provider ID for ABDM bridge registration. Defaults to `hipId`. |
| `facilityName` | No | Facility display name for bridge registration. Defaults to `hospitalName`. |
| `hrp` | No | Custom HRP service list. Leave as an empty array to let the backend create the HIP service object from `hipId` and `hiuId`. |

Success response:

```json
{
  "hospitalId": "<hospitalId>",
  "loginId": "<loginId>",
  "hospitalName": "<hospitalName>",
  "apiKey": "<apiKey>",
  "environment": "<environment>",
  "message": "Hospital registered successfully. Save the apiKey; it is shown only once.",
  "bridgeSetup": {
    "status": "<bridgeSetupStatus>"
  }
}
```

### 3. Register Only Without Bridge Setup

Prefer `POST /v1/admin/customers`. Use this only when bridge setup is not needed.

```http
POST <baseUrl>/v1/auth/register
Authorization: Bearer <adminKey>
Content-Type: application/json
```

Request body:

```json
{
  "loginId": "<loginId>",
  "password": "<password>",
  "hospitalName": "<hospitalName>",
  "hipId": "<hipId>",
  "hiuId": "<hiuId>",
  "webhookUrl": "<webhookUrl>",
  "webhookSecret": "<webhookSecret>"
}
```

Fields have the same definitions as customer creation.

Success response:

```json
{
  "hospitalId": "<hospitalId>",
  "loginId": "<loginId>",
  "hospitalName": "<hospitalName>",
  "apiKey": "<apiKey>",
  "environment": "<environment>",
  "message": "Hospital registered successfully. Save the apiKey; it is shown only once."
}
```

### 4. Update ABDM Callback URL

```http
PATCH <baseUrl>/v1/admin/bridge/callback-url
Authorization: Bearer <adminKey>
Content-Type: application/json
```

Request body:

```json
{
  "callbackUrl": "<callbackUrl>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `callbackUrl` | Yes | HTTPS URL where ABDM sends bridge callbacks. |

Success response: Pass-through ABDM gateway response for callback URL update, or:

```json
{
  "status": "ok"
}
```

### 5. Register ABDM Bridge Services

```http
POST <baseUrl>/v1/admin/bridge/register-services
Authorization: Bearer <adminKey>
Content-Type: application/json
```

Request body:

```json
{
  "facilityId": "<facilityId>",
  "facilityName": "<facilityName>",
  "hrp": [
    {
      "id": "<facilityId>",
      "name": "<facilityName>",
      "type": "HIP",
      "isActive": true,
      "endpoints": [
        {
          "use": "KYC_AND_LINKING",
          "type": "FHIR",
          "bridge": "<callbackUrl>"
        }
      ]
    }
  ]
}
```

| Field | Required | Definition |
|---|---:|---|
| `facilityId` | Yes | ABDM facility/provider ID. |
| `facilityName` | Yes | ABDM facility display name. |
| `hrp` | Yes | List of Health Record Provider service objects registered with ABDM. |
| `hrp[].id` | Yes | Service/facility ID. |
| `hrp[].name` | Yes | Service display name. |
| `hrp[].type` | Yes | Service type. Expected values depend on ABDM registration, commonly `HIP`, `HIU`, or combined HIP/HIU service type. |
| `hrp[].isActive` | No | Whether the service is active. |
| `hrp[].endpoints` | Yes | Service endpoint list. |
| `hrp[].endpoints[].use` | Yes | ABDM endpoint purpose, for example linking/KYC. |
| `hrp[].endpoints[].type` | Yes | Endpoint payload type, for example `FHIR`. |
| `hrp[].endpoints[].bridge` | Yes | Callback bridge URL. |

Success response: Pass-through ABDM facility bridge response.

### 6. List ABDM Bridge Services

```http
GET <baseUrl>/v1/admin/bridge/services
Authorization: Bearer <adminKey>
```

Success response: Pass-through ABDM bridge services response.

### 7. Test ABDM Gateway Token Fetch

```http
POST <baseUrl>/v1/admin/abdm/test-token
Authorization: Bearer <adminKey>
```

Success response when the token fetch succeeds:

```json
{
  "ok": true,
  "statusCode": 200,
  "url": "<abdmGatewaySessionUrl>",
  "clientId": "<abdmClientId>",
  "cmId": "<cmId>",
  "timestamp": "<timestamp>",
  "body": "<abdmResponseBody>"
}
```

Success response when the diagnostic call completes but ABDM rejects the token request:

```json
{
  "ok": false,
  "statusCode": "<upstreamStatusCode>",
  "url": "<abdmGatewaySessionUrl>",
  "clientId": "<abdmClientId>",
  "cmId": "<cmId>",
  "timestamp": "<timestamp>",
  "body": "<abdmResponseBody>"
}
```

### 8. Manually Set ABDM Gateway Token

Use this only when automatic ABDM session token fetch is blocked.

```http
PUT <baseUrl>/v1/admin/abdm/gateway-token
Authorization: Bearer <adminKey>
Content-Type: application/json
```

Request body:

```json
{
  "token": "<abdmGatewayToken>",
  "expiresIn": 1800
}
```

| Field | Required | Definition |
|---|---:|---|
| `token` | Yes | Valid ABDM gateway bearer token. |
| `expiresIn` | No | Token lifetime in seconds. Allowed range is 60 to 86400. Defaults to 1800. |

Success response:

```json
{
  "status": "ok",
  "expiresIn": 1800
}
```

## Flow 2: Customer Auth and Webhook Setup

### 1. Login

Login verifies credentials. It does not issue or rotate the API key.

```http
POST <baseUrl>/v1/auth/login
Content-Type: application/json
```

Request body:

```json
{
  "loginId": "<loginId>",
  "password": "<password>"
}
```

Success response:

```json
{
  "hospitalId": "<hospitalId>",
  "loginId": "<loginId>",
  "hospitalName": "<hospitalName>",
  "environment": "<environment>",
  "message": "Login successful. Use your existing API key for all requests. To issue a new key call POST /v1/auth/rotate-key."
}
```

### 2. Get Authenticated Hospital Profile

```http
GET <baseUrl>/v1/auth/me
Authorization: Bearer <apiKey>
```

Success response:

```json
{
  "hospitalId": "<hospitalId>",
  "loginId": "<loginId>",
  "hospitalName": "<hospitalName>",
  "environment": "<environment>",
  "hipId": "<hipId>",
  "hiuId": "<hiuId>",
  "webhookUrl": "<webhookUrl>",
  "dataPushUrl": "<dataPushUrl>",
  "createdAt": "<createdAt>",
  "updatedAt": "<updatedAt>"
}
```

### 3. Rotate API Key

```http
POST <baseUrl>/v1/auth/rotate-key
Authorization: Bearer <apiKey>
```

Success response:

```json
{
  "hospitalId": "<hospitalId>",
  "loginId": "<loginId>",
  "hospitalName": "<hospitalName>",
  "apiKey": "<newApiKey>",
  "environment": "<environment>",
  "message": "API key rotated successfully. Save the new apiKey; it is shown only once."
}
```

### 4. Configure Webhook Endpoint

```http
PUT <baseUrl>/v1/webhook-endpoint
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "webhookUrl": "<webhookUrl>",
  "webhookSecret": "<webhookSecret>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `webhookUrl` | Yes | HTTPS URL where Sahai sends customer events. |
| `webhookSecret` | Yes | Secret for verifying HMAC-SHA256 webhook signatures. Minimum 16 characters. |

Success response:

```json
{
  "status": "ok",
  "webhookUrl": "<webhookUrl>"
}
```

### 5. Test Webhook Endpoint

```http
POST <baseUrl>/v1/webhook-endpoint/test
Authorization: Bearer <apiKey>
```

Success response:

```json
{
  "status": "ok",
  "webhookStatusCode": "<webhookStatusCode>"
}
```

### 6. Configure Data Push Endpoint

```http
PUT <baseUrl>/v1/data-push-endpoint
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "dataPushUrl": "<dataPushUrl>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `dataPushUrl` | Yes | HTTPS URL where the HIP pushes encrypted health information directly to the hospital's own system. |

Once configured, `POST /v1/health-information` uses this URL automatically: the HIP delivers the encrypted FHIR payload straight to the hospital and Sahai never receives or stores the health data. Decrypt the received payload with `POST /v1/health-information/decrypt` — the ECDH key session stays at Sahai.

If no data-push endpoint is registered, data is pushed to Sahai's own `/data` endpoint, decrypted there, and retrieved with `GET /v1/health-records/<trackingId>/decrypt`.

The URL can also be set at registration (`dataPushUrl` field on `POST /v1/auth/register` and `POST /v1/admin/customers`) and is visible on `GET /v1/auth/me`.

Success response:

```json
{
  "status": "ok",
  "dataPushUrl": "<dataPushUrl>"
}
```

## Flow 3: ABHA Enrollment and Profile

All APIs in this flow require `Authorization: Bearer <apiKey>`.

### 1. Aadhaar Enrollment - Request OTP

```http
POST <baseUrl>/v1/abha/enroll/aadhaar/request-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "aadhaar": "<aadhaar>",
  "txnId": "<txnId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `aadhaar` | Yes | Patient 12-digit Aadhaar number. Backend encrypts it before sending to ABDM. |
| `txnId` | No | Existing ABDM transaction ID when continuing a session. Send empty string or omit if starting a new session. |

Success response: Pass-through ABDM ABHA enrollment OTP response. See `ABDM Pass-Through Responses`.

### 2. Aadhaar Enrollment - Verify OTP

```http
POST <baseUrl>/v1/abha/enroll/aadhaar/verify-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>",
  "otp": "<otp>",
  "mobile": "<mobile>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `txnId` | Yes | Transaction ID from the Aadhaar OTP request. |
| `otp` | Yes | OTP entered by patient. Length 4 to 8 characters. |
| `mobile` | No | Patient mobile number if ABDM requires it for enrollment completion. |

Success response: Pass-through ABDM ABHA enrollment response. See `ABDM Pass-Through Responses`.

### 3. Mobile Enrollment - Request OTP

```http
POST <baseUrl>/v1/abha/enroll/mobile/request-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "mobile": "<mobile>",
  "txnId": "<txnId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `mobile` | Yes | Patient 10-digit mobile number. |
| `txnId` | No | Existing ABDM transaction ID if continuing a session. |

Success response: Pass-through ABDM OTP response. See `ABDM Pass-Through Responses`.

### 4. Mobile Enrollment - Verify OTP

```http
POST <baseUrl>/v1/abha/enroll/mobile/verify-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>",
  "otp": "<otp>"
}
```

Success response: Pass-through ABDM mobile verification response. See `ABDM Pass-Through Responses`.

### 5. Get ABHA Address Suggestions

```http
POST <baseUrl>/v1/abha/address/suggestions
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `txnId` | Yes | Enrollment transaction ID. |

Success response: Pass-through ABDM ABHA address suggestion response. See `ABDM Pass-Through Responses`.

### 6. Set ABHA Address

```http
POST <baseUrl>/v1/abha/address/set
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>",
  "abhaAddress": "<abhaAddress>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `txnId` | Yes | Enrollment transaction ID. |
| `abhaAddress` | Yes | Patient-selected ABHA address from suggestions. |

Success response: Pass-through ABDM address-set response. See `ABDM Pass-Through Responses`.

### 7. Existing ABHA Lookup - Request OTP

```http
POST <baseUrl>/v1/abha/lookup/request-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "loginHint": "<loginHint>",
  "loginId": "<loginIdValue>",
  "otpSystem": "<otpSystem>",
  "txnId": "<txnId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `loginHint` | Yes | Login type: `mobile`, `aadhaar`, `abha-number`, or `abha-address`. |
| `loginId` | Yes | Value matching `loginHint`. Backend encrypts it before sending to ABDM. |
| `otpSystem` | No | OTP system. Usually `abdm` or `aadhaar`. Defaults to `abdm`. |
| `txnId` | No | Existing ABDM transaction ID if continuing a session. |

Success response: Pass-through ABDM lookup OTP response. See `ABDM Pass-Through Responses`.

### 8. Existing ABHA Lookup - Verify OTP

```http
POST <baseUrl>/v1/abha/lookup/verify-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>",
  "otp": "<otp>",
  "loginHint": "<loginHint>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `txnId` | Yes | Transaction ID from lookup OTP request. |
| `otp` | Yes | OTP entered by patient. |
| `loginHint` | No | Same login hint used for the request. Defaults to `mobile`. |

Success response: Pass-through ABDM profile/login response. Use the returned token as `<xToken>` when fetching profile, card, or QR. See `ABDM Pass-Through Responses`.

### 9. Search ABHA by Mobile

```http
POST <baseUrl>/v1/abha/search/by-mobile
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "mobile": "<mobile>"
}
```

Success response: Pass-through ABDM list of ABHA accounts linked to the mobile number. See `ABDM Pass-Through Responses`.

### 10. Search ABHA by ABHA Number

```http
POST <baseUrl>/v1/abha/search/by-abha-number
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaNumber": "<abhaNumber>"
}
```

Success response: Pass-through ABDM profile lookup response. See `ABDM Pass-Through Responses`.

### 11. PHR Search by ABHA Address

```http
POST <baseUrl>/v1/abha/phr/search
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>"
}
```

Success response: Pass-through ABDM PHR search response. See `ABDM Pass-Through Responses`.

### 12. PHR Send OTP

```http
POST <baseUrl>/v1/abha/phr/send-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>",
  "txnId": "<txnId>",
  "otpSystem": "<otpSystem>"
}
```

Success response: Pass-through ABDM PHR OTP response. See `ABDM Pass-Through Responses`.

### 13. PHR Verify OTP

```http
POST <baseUrl>/v1/abha/phr/verify-otp
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "txnId": "<txnId>",
  "otp": "<otp>"
}
```

Success response: Pass-through ABDM PHR verification response. See `ABDM Pass-Through Responses`.

### 14. Get ABHA Profile Details

```http
POST <baseUrl>/v1/abha/profile/details
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "xToken": "<xToken>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `xToken` | Yes | Token returned by ABDM verify/login flow. |

Success response: Pass-through ABDM profile response. See `ABDM Pass-Through Responses`.

### 15. Download ABHA Card

```http
POST <baseUrl>/v1/abha/profile/card
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "xToken": "<xToken>"
}
```

Success response:

```text
Content-Type: application/pdf
<binary PDF body>
```

### 16. Download ABHA QR Code

```http
POST <baseUrl>/v1/abha/profile/qr-code
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "xToken": "<xToken>"
}
```

Success response:

```text
Content-Type: image/png
<binary PNG body>
```

## Flow 4: HIP-Initiated Care Context Linking

### 1. Request Link Token

This is a demographics-based link-token request. ABDM accepts the request and sends the link token asynchronously through callback.

```http
POST <baseUrl>/v1/link-token
Authorization: Bearer <apiKey>
Idempotency-Key: <idempotencyKey>
Content-Type: application/json
```

Request body:

```json
{
  "hipId": "<hipId>",
  "abhaAddress": "<abhaAddress>",
  "abhaNumber": "<abhaNumber>",
  "patientReference": "<patientReference>",
  "name": "<patientName>",
  "gender": "<gender>",
  "yearOfBirth": "<yearOfBirth>",
  "purpose": "LINK_CARE_CONTEXT"
}
```

| Field | Required | Definition |
|---|---:|---|
| `hipId` | Yes | ABDM HIP ID for the hospital/facility. |
| `abhaAddress` | Yes | Patient ABHA address. |
| `abhaNumber` | No | Patient ABHA number. Hyphens are removed before ABDM dispatch. |
| `patientReference` | Yes | Hospital-side patient reference. |
| `name` | Yes | Patient name as used for ABDM demographics match. |
| `gender` | No | Patient gender value expected by ABDM. |
| `yearOfBirth` | No | Patient birth year. Must be between 1900 and 2100. |
| `purpose` | No | Purpose for token generation. Defaults to `LINK_CARE_CONTEXT`. |

Success response: HTTP `202`.

```json
{
  "trackingId": "<trackingId>",
  "requestId": "<requestId>",
  "status": "accepted"
}
```

Failure examples:

```json
{
  "errorCode": "IDEMPOTENCY_KEY_REQUIRED",
  "message": "Idempotency-Key header is required",
  "details": {}
}
```

```json
{
  "errorCode": "IDEMPOTENCY_CONFLICT",
  "message": "Idempotency key was already used with a different request",
  "details": {}
}
```

### 2. Poll Request Status

```http
GET <baseUrl>/v1/status/<trackingId>
Authorization: Bearer <apiKey>
```

Success response:

```json
{
  "trackingId": "<trackingId>",
  "status": "<status>",
  "eventType": "<eventType>",
  "details": {}
}
```

| Field | Definition |
|---|---|
| `trackingId` | Tracking ID from an async API. |
| `status` | Current processing state, such as `accepted`, `dispatched`, `dispatchFailed`, or callback-updated status. |
| `eventType` | Backend event type for the tracked flow. |
| `details` | Flow-specific details such as step, ABDM request ID, transaction ID, or error text. |

Status values are written by different parts of the system. Treat unknown future values as non-terminal unless `details.error` is present.

| status | Written when | Terminal | Client action |
|---|---|---:|---|
| `accepted` | Sahai accepted and stored an async request. | No | Continue polling. |
| `dispatched` | Sahai sent the outbound request to ABDM. | No | Wait for ABDM callback/webhook or later status. |
| `dispatchFailed` | Sahai could not send the request to ABDM. | Yes | Stop polling and inspect `details.error`. |
| `callbackReceived` | ABDM callback matched the request, but no specific acknowledgement status was found. | Usually yes | Stop automatic polling; inspect webhook `payload` and `details.callbackId`. |
| `failed` | Callback had an `error` object or a data-flow job failed. | Yes | Stop polling and inspect `details`. |
| `success` | ABDM callback acknowledgement status was `SUCCESS`. | Yes | Stop polling for that request. |
| `ok` | ABDM callback acknowledgement status was `OK`. | Yes | Stop polling for that request. |
| `decrypted` | Encrypted health data was received and at least one entry was decrypted. | Yes | Call `GET /v1/health-records/<trackingId>/decrypt`. |
| `encryptedStored` | Encrypted health data was stored but not decrypted. | Usually terminal for the current attempt | Inspect `details.errors`; retry only after fixing key/correlation issue. |
| `pushed` | HIP data-flow job pushed health information to the requested `dataPushUrl`. | Yes | Stop polling. |
| `skipped` | Data-flow job type was unsupported or intentionally skipped. | Yes | Inspect `details.errors`. |

Recommended polling stop rules:

| Flow | Stop when |
|---|---|
| Link token / care-context linking | `dispatchFailed`, `callbackReceived`, `success`, `ok`, or `failed`. |
| Consent request | `eventType` is `consent.granted` or `consent.denied`, or `status` is `failed` or `dispatchFailed`. |
| Health-information request as HIU | `decrypted`, `encryptedStored`, `failed`, or `dispatchFailed`. |
| HIP data push to another HIU | `pushed` or `failed`. |

### 3. Fetch Available Auth Modes

```http
POST <baseUrl>/v1/hip/link/fetch-modes
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>",
  "purpose": "LINK"
}
```

| Field | Required | Definition |
|---|---:|---|
| `abhaAddress` | Yes | Patient ABHA address. |
| `purpose` | No | ABDM auth purpose. Defaults to `LINK`. |

Success response: Pass-through ABDM gateway response or empty object when ABDM returns no body. See `ABDM Pass-Through Responses`.

### 4. Initiate OTP Linking

```http
POST <baseUrl>/v1/hip/link/otp-init
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>",
  "authMode": "MOBILE_OTP",
  "purpose": "LINK"
}
```

| Field | Required | Definition |
|---|---:|---|
| `abhaAddress` | Yes | Patient ABHA address. |
| `authMode` | No | ABDM auth mode, default `MOBILE_OTP`. |
| `purpose` | No | ABDM auth purpose, default `LINK`. |

Success response: Pass-through ABDM gateway response or empty object. ABDM returns transaction details through callback. See `ABDM Pass-Through Responses`.

### 5. Confirm OTP Linking

```http
POST <baseUrl>/v1/hip/link/otp-confirm
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "transactionId": "<transactionId>",
  "otp": "<otp>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | Yes | Transaction ID from ABDM link-init callback. |
| `otp` | Yes | OTP entered by patient. |

Success response: Pass-through ABDM gateway response or empty object. ABDM delivers `linkToken` through callback on success. See `ABDM Pass-Through Responses`.

### 6. Link Care Contexts

```http
POST <baseUrl>/v1/care-contexts/link
Authorization: Bearer <apiKey>
Idempotency-Key: <idempotencyKey>
Content-Type: application/json
```

Request body:

```json
{
  "hipId": "<hipId>",
  "abhaAddress": "<abhaAddress>",
  "abhaNumber": "<abhaNumber>",
  "patientReference": "<patientReference>",
  "linkToken": "<linkToken>",
  "careContexts": [
    {
      "reference": "<careContextReference>",
      "display": "<careContextDisplay>",
      "hiTypes": ["<hiType>"],
      "clinicalPayload": {},
      "documentData": "<documentData>",
      "documentTitle": "<documentTitle>",
      "documentContentType": "<documentContentType>"
    }
  ]
}
```

| Field | Required | Definition |
|---|---:|---|
| `hipId` | Yes | ABDM HIP ID. |
| `abhaAddress` | Yes | Patient ABHA address. |
| `abhaNumber` | No | Patient ABHA number. |
| `patientReference` | Yes | Hospital-side patient reference. |
| `linkToken` | No | ABDM link token. Required by ABDM when the selected linking method needs `X-link-token`. |
| `careContexts` | Yes | One or more care contexts to store locally and send to ABDM. |
| `careContexts[].reference` | Yes | Hospital-side care context reference. |
| `careContexts[].display` | Yes | Human-readable care context display label. |
| `careContexts[].hiTypes` | No | Health information types for this context. Use ABDM-valid values: `OPConsultation`, `DiagnosticReport`, `DischargeSummary`, `Prescription`, `ImmunizationRecord`, `HealthDocumentRecord`, `WellnessRecord`, `Invoice`. `OPDocumentRecord` is not accepted by ABDM. |
| `careContexts[].clinicalPayload` | No | Structured clinical data stored locally for later health-information push. Send `{}` for HIP-initiated linking without immediate data push (M2). |
| `careContexts[].documentData` | No | Document payload, if a document is stored with the care context. |
| `careContexts[].documentTitle` | No | Document title. |
| `careContexts[].documentContentType` | No | MIME type of `documentData`. |

Notes for `abhaNumber`: omit this field or send `null` if the patient ABHA number is not available. The `abhaAddress` alone is sufficient for ABDM to identify the patient.

Success response: HTTP `202`.

```json
{
  "trackingId": "<trackingId>",
  "requestId": "<requestId>",
  "status": "accepted"
}
```

### 7. Notify ABDM That Care Context Was Linked

```http
POST <baseUrl>/v1/hip/link/care-context/notify
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>",
  "patientReference": "<patientReference>",
  "careContextReference": "<careContextReference>",
  "hiTypes": ["<hiType>"],
  "linkToken": "<linkToken>"
}
```

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

### 8. Send Deep-Link SMS

```http
POST <baseUrl>/v1/hip/sms-notify
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "phoneNo": "<phoneNo>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `phoneNo` | Yes | Patient mobile number with country code. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

## Flow 5: User-Initiated Linking Responses

Use these after your HMS receives ABDM user-initiated linking callbacks. These request models allow extra ABDM-specific fields because callback payloads can vary.

### 1. Respond to Discovery

```http
POST <baseUrl>/v1/user-linking/on-discover
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "transactionId": "<transactionId>",
  "patient": {
    "referenceNumber": "<patientReference>",
    "display": "<patientDisplay>",
    "careContexts": [
      {
        "referenceNumber": "<careContextReference>",
        "display": "<careContextDisplay>"
      }
    ],
    "hiType": "<hiType>",
    "count": "<careContextCount>"
  },
  "resp": {
    "requestId": "<requestId>"
  }
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | Yes | Transaction ID from ABDM discovery callback. |
| `patient` | No | Patient match response. Send a patient object when the hospital found a matching patient; send `null` or omit when no patient is found, according to the ABDM callback handling agreed for the integration. |
| `patient.referenceNumber` | Yes when `patient` is sent | Hospital-side patient reference. |
| `patient.display` | Recommended | Patient display label shown to the user. |
| `patient.careContexts` | Recommended | Care contexts available for linking. |
| `patient.careContexts[].referenceNumber` | Yes when care context is sent | Hospital-side care context reference. |
| `patient.careContexts[].display` | Yes when care context is sent | Human-readable care context display label. |
| `patient.hiType` | Optional | ABDM health information type when the response is for a single type. Some ABDM versions expect `hiTypes` instead; this endpoint allows extra fields for that reason. |
| `patient.count` | Optional | Number of matching care contexts. |
| `resp.requestId` | Recommended | Original ABDM callback request ID for correlation. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

### 2. Respond to Link Init

```http
POST <baseUrl>/v1/user-linking/on-init
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "transactionId": "<transactionId>",
  "link": {
    "referenceNumber": "<linkReferenceNumber>",
    "authenticationType": "DIRECT",
    "meta": {
      "communicationMedium": "MOBILE",
      "communicationHint": "<communicationHint>",
      "communicationExpiry": "<communicationExpiryTimestamp>"
    }
  },
  "resp": {
    "requestId": "<requestId>"
  }
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | Yes | Transaction ID from ABDM link-init callback. |
| `link` | No | Link-init response details. Use it to tell ABDM the link/auth reference generated by the hospital. |
| `link.referenceNumber` | Recommended | Hospital-generated link reference or OTP reference. Use the same value later when confirming the link, if required by the ABDM flow. |
| `link.authenticationType` | Optional | Authentication type used by the hospital, for example direct or OTP-based, as agreed for the ABDM integration. |
| `link.meta` | Optional | Communication metadata for the patient authentication step. |
| `link.meta.communicationMedium` | Optional | Channel used to contact the patient, for example mobile. |
| `link.meta.communicationHint` | Optional | Masked destination or instruction shown to the patient. |
| `link.meta.communicationExpiry` | Optional | ISO 8601 expiry timestamp for the authentication step. |
| `resp.requestId` | Recommended | Original ABDM callback request ID for correlation. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

### 3. Respond to Link Confirm

```http
POST <baseUrl>/v1/user-linking/on-confirm
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "transactionId": "<transactionId>",
  "patient": {
    "referenceNumber": "<patientReference>",
    "display": "<patientDisplay>",
    "careContexts": [
      {
        "referenceNumber": "<careContextReference>",
        "display": "<careContextDisplay>"
      }
    ]
  },
  "resp": {
    "requestId": "<requestId>"
  }
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | Yes | Transaction ID from ABDM link-confirm callback. |
| `patient` | No | Final patient and care-context confirmation payload. |
| `patient.referenceNumber` | Yes when `patient` is sent | Hospital-side patient reference being linked. |
| `patient.display` | Recommended | Patient display label. |
| `patient.careContexts` | Recommended | Care contexts approved for final linking. |
| `patient.careContexts[].referenceNumber` | Yes when care context is sent | Hospital-side care context reference. |
| `patient.careContexts[].display` | Yes when care context is sent | Human-readable care context display label. |
| `resp.requestId` | Recommended | Original ABDM callback request ID for correlation. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

## Flow 6: HIU Consent and Health Information

### 1. Request Consent

```http
POST <baseUrl>/v1/consents
Authorization: Bearer <apiKey>
Idempotency-Key: <idempotencyKey>
Content-Type: application/json
```

Request body:

```json
{
  "abhaAddress": "<abhaAddress>",
  "patientReference": "<patientReference>",
  "hiuId": "<hiuId>",
  "purpose": {
    "text": "<purposeText>",
    "code": "<purposeCode>",
    "refUri": "www.abdm.gov.in"
  },
  "requester": {
    "name": "<requesterName>",
    "type": "<requesterIdentifierType>",
    "value": "<requesterIdentifierValue>",
    "system": "<requesterIdentifierSystem>"
  },
  "hiTypes": ["<hiType>"],
  "dateRange": {
    "from": "<fromTimestamp>",
    "to": "<toTimestamp>"
  },
  "permission": {
    "accessMode": "VIEW",
    "dataEraseAt": "<dataEraseAtTimestamp>",
    "frequency": {
      "unit": "HOUR",
      "value": 0,
      "repeats": 0
    }
  }
}
```

| Field | Required | Definition |
|---|---:|---|
| `abhaAddress` | Yes | Patient ABHA address. |
| `patientReference` | Yes | Hospital-side patient identifier. Required so consent status webhooks and decrypt responses can map ABDM data back to the hospital patient record. |
| `hiuId` | No | HIU ID for this request. Falls back to the HIU ID registered with your API key; `403 FORBIDDEN` when neither exists. |
| `purpose` | Yes | ABDM consent purpose object. |
| `purpose.text` | Yes | Consent purpose display text. |
| `purpose.code` | Yes | ABDM purpose code. |
| `purpose.refUri` | Yes | ABDM purpose reference URI. Must not be blank — ABDM rejects it (`ABDM-9999 Invalid consent purpose refURI`); the backend returns `422` upfront. Standard value: `www.abdm.gov.in`. |
| `requester` | Yes | Identity of the clinician/system initiating this specific request. Varies per request, so it is not derived from the API key. |
| `requester.name` | Yes | Name of the consent requester. |
| `requester.type` | Yes | Identifier type for the requester, e.g. `REGNO`, `HPR`. |
| `requester.value` | Yes | Identifier value for the requester. |
| `requester.system` | Yes | Identifier system/issuing authority for the requester. |
| `hiTypes` | Yes | Health information types requested. Must contain at least one item. |
| `dateRange.from` | Yes | Start timestamp for records requested. |
| `dateRange.to` | Yes | End timestamp for records requested. |
| `permission.accessMode` | No | Access mode. Backend defaults to `VIEW`. |
| `permission.dataEraseAt` | No | Timestamp after which data must be erased. Defaults to `dateRange.to` if missing. |
| `permission.frequency.unit` | No | Frequency unit. Defaults to `HOUR`. |
| `permission.frequency.value` | No | Frequency value. Defaults to `0`. |
| `permission.frequency.repeats` | No | Number of repeats. Defaults to `0`. |

Success response: HTTP `202`.

```json
{
  "trackingId": "<trackingId>",
  "requestId": "<requestId>",
  "status": "accepted"
}
```

### 2. Check Consent Status

```http
POST <baseUrl>/v1/consents/status
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "consentRequestId": "<consentRequestId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `consentRequestId` | Yes | ABDM consent request ID. |

`hiuId` may be passed in the body; when omitted it falls back to the HIU ID registered with your API key, same as Request Consent above.

Success response: Pass-through ABDM consent status response, commonly including statuses such as `REQUESTED`, `GRANTED`, `DENIED`, or `EXPIRED`. See `ABDM Pass-Through Responses`.

### 3. Fetch Consent Artefact

```http
POST <baseUrl>/v1/consents/fetch
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "consentId": "<consentId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `consentId` | Yes | ABDM consent artefact ID from the granted consent callback. |

`hiuId` may be passed in the body; when omitted it falls back to the HIU ID registered with your API key, same as Request Consent above.

Success response: Pass-through ABDM consent artefact response. See `ABDM Pass-Through Responses`.

### 4. Request Health Information

```http
POST <baseUrl>/v1/health-information
Authorization: Bearer <apiKey>
Idempotency-Key: <idempotencyKey>
Content-Type: application/json
```

Request body:

```json
{
  "consentId": "<consentId>",
  "dateRange": {
    "from": "<fromTimestamp>",
    "to": "<toTimestamp>"
  },
  "dataPushUrl": "<dataPushUrl>",
  "transactionId": "<transactionId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `consentId` | Yes | ABDM consent artefact ID. |
| `dateRange.from` | Yes | Start timestamp for health records requested. |
| `dateRange.to` | Yes | End timestamp for health records requested. |
| `dataPushUrl` | No | HTTPS endpoint where HIP pushes encrypted health data. Resolution order: this field → hospital's registered data-push endpoint (`PUT /v1/data-push-endpoint`) → Sahai's own `/data` endpoint. |
| `transactionId` | No | Client-supplied transaction ID. Backend generates one if omitted. |

When data is pushed to the hospital's own endpoint (options 1 and 2), Sahai never receives or stores the health data — decrypt the received payload with `POST /v1/health-information/decrypt`. When it goes to Sahai's `/data` endpoint (option 3), Sahai decrypts and stores it — retrieve with `GET /v1/health-records/<trackingId>/decrypt`.

`hiuId` may be passed in the body; when omitted it falls back to the HIU ID registered with your API key, same as Request Consent above.

Success response: HTTP `202`.

```json
{
  "trackingId": "<trackingId>",
  "requestId": "<requestId>",
  "status": "accepted"
}
```

### 5. Get Health Record Result

```http
GET <baseUrl>/v1/health-records/<trackingId>
Authorization: Bearer <apiKey>
```

Returns HTTP `404` when the tracking ID does not exist for this hospital.

Success response while data has not arrived yet (request accepted or dispatched):

```json
{
  "trackingId": "<trackingId>",
  "status": "pending",
  "result": {
    "details": {}
  }
}
```

If the ABDM dispatch failed, `status` is `dispatchFailed` and `result.details` carries the error.

Success response once data has been received:

```json
{
  "trackingId": "<trackingId>",
  "status": "decrypted",
  "result": {
    "decryptedCount": "<decryptedCount>",
    "records": [
      {
        "recordId": "<recordId>",
        "careContextReference": "<careContextReference>",
        "media": "<mediaType>",
        "transactionId": "<transactionId>",
        "createdAt": "<createdAt>"
      }
    ],
    "details": {},
    "receivedAt": "<receivedAt>",
    "entryCount": "<entryCount>",
    "transactionId": "<transactionId>"
  }
}
```

| Field | Definition |
|---|---|
| `trackingId` | Tracking ID from health-information request. |
| `status` | `pending`, `dispatchFailed`, `encryptedStored` (arrived but nothing decrypted), or `decrypted`. |
| `result.decryptedCount` | Number of entries decrypted and stored. |
| `result.records[]` | Summary of each decrypted record. Fetch the FHIR content with `/decrypt`. |
| `result.details` | Latest processing details, including per-entry decryption errors if any. |
| `result.receivedAt` | ISO 8601 timestamp when Sahai received the data push. |
| `result.entryCount` | Number of encrypted entries received from the HIP. |

### 6. Get Decrypted Health Records

```http
GET <baseUrl>/v1/health-records/<trackingId>/decrypt
Authorization: Bearer <apiKey>
```

Error responses: HTTP `404` when the tracking ID is unknown or data has not arrived yet (the message distinguishes the two); HTTP `424` with code `DATA_DECRYPTION_FAILED` when data arrived but could not be decrypted (per-entry errors included).

Every successful call is written to Sahai's access-audit trail (who fetched which tracking ID, when).

Success response:

```json
{
  "trackingId": "<trackingId>",
  "status": "decrypted",
  "entryCount": "<entryCount>",
  "readErrorCount": 0,
  "entries": [
    {
      "careContextReference": "<careContextReference>",
      "media": "<mediaType>",
      "fhir": {}
    }
  ]
}
```

| Field | Definition |
|---|---|
| `entryCount` | Number of decrypted FHIR entries returned. |
| `readErrorCount` | Number of entries whose stored content could not be read back. Those entries carry an `error` field and an empty `fhir`. |
| `entries[].careContextReference` | Care context reference for the decrypted record. |
| `entries[].media` | Media type of the decrypted record. |
| `entries[].fhir` | Decrypted FHIR JSON loaded from backend storage. |
| `entries[].error` | Present only when this entry's stored content failed to load. |

### 7. Decrypt Health Information (Direct Push)

```http
POST <baseUrl>/v1/health-information/decrypt
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Use this when the HIP pushed encrypted data directly to your registered data-push endpoint (`PUT /v1/data-push-endpoint`). Forward the push payload unchanged — Sahai looks up the ECDH key session for the matching request (scoped to your hospital), decrypts, and returns the plaintext. The keys never leave Sahai and the decrypted data is not stored; every call is written to the access-audit trail.

Request body:

```json
{
  "transactionId": "<transactionId>",
  "consentId": "<consentId>",
  "entries": [
    {
      "content": "<base64-ciphertext>",
      "media": "application/fhir+json",
      "checksum": "<checksum>",
      "careContextReference": "<careContextReference>"
    }
  ],
  "keyMaterial": {
    "cryptoAlg": "ECDH",
    "curve": "Curve25519",
    "dhPublicKey": {
      "keyValue": "<sender-public-key>"
    },
    "nonce": "<sender-nonce>"
  }
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | One of these | ABDM transaction ID from the push. Provide this or `consentId` so the key session can be found. |
| `consentId` | One of these | Consent artefact ID tied to the original request. |
| `entries` | Yes | Encrypted entries exactly as received from the HIP. Minimum one. |
| `entries[].content` | Yes | Base64 ciphertext. |
| `keyMaterial` | Yes | `keyMaterial` object from the push. `dhPublicKey.keyValue` and `nonce` are required. |

Error responses: HTTP `404` when no matching health-information request exists for this hospital; HTTP `410` when the key session has expired (key sessions live 30 days — decrypt promptly); HTTP `422` when identifiers or key material are missing.

Success response:

```json
{
  "trackingId": "<trackingId>",
  "transactionId": "<transactionId>",
  "entryCount": 1,
  "decryptedCount": 1,
  "errors": [],
  "entries": [
    {
      "careContextReference": "<careContextReference>",
      "media": "application/fhir+json",
      "fhir": {}
    }
  ]
}
```

Entries that fail to decrypt carry an `error` field instead of `fhir`. If the plaintext is not valid JSON it is returned under `raw` instead of `fhir`.

`entries[].fhir` is a FHIR R4 document `Bundle`. The exact resources depend on what was pushed by the HIP or built from the stored care context:

| fhir field | Definition |
|---|---|
| `resourceType` | Always `Bundle` for records generated by this backend. |
| `id` | Bundle ID generated by Sahai or the sending HIP. |
| `type` | Bundle type, normally `document`. |
| `identifier.system` | Identifier namespace. This backend uses `http://hip.in` for generated bundles. |
| `identifier.value` | Care context reference used as the document identifier. |
| `meta.profile` | ABDM/NRCES FHIR profile URL, usually `DocumentBundle`. |
| `meta.security` | Confidentiality marking. Generated bundles use `V` / very restricted. |
| `meta.tag` | Backend metadata, including Sahai hospital ID for generated bundles. |
| `entry[]` | FHIR resources inside the document bundle. |
| `entry[].resource.resourceType` | Resource type, such as `Composition`, `Patient`, `Practitioner`, `DocumentReference`, `Basic`, or a clinical resource from `clinicalPayload`. |
| `Composition` | Document header resource. Contains `status`, document `type`, `date`, `subject`, `author`, `title`, and `section`. |
| `Patient` | Patient resource. Generated bundles currently create a minimal patient resource. |
| `Practitioner` | Practitioner resource. Generated bundles currently create a minimal practitioner resource. |
| `DocumentReference` | Present when the care context was stored with PDF/document data. Contains attachment content type, base64 document data, and title. |
| `Basic` or clinical resource | Present when care context `clinicalPayload` is used. If no clinical payload exists, backend generates a fallback `Basic` resource saying clinical payload is unavailable. |

Generated bundle profiles by `hiType`:

| ABDM hiType (send in request) | NRCES FHIR Composition profile |
|---|---|
| `OPConsultation` | `OPConsultRecord` |
| `DiagnosticReport` | `DiagnosticReportRecord` |
| `DischargeSummary` | `DischargeSummaryRecord` |
| `Prescription` | `PrescriptionRecord` |
| `ImmunizationRecord` | `ImmunizationRecord` |
| `HealthDocumentRecord` | `HealthDocumentRecord` |
| `WellnessRecord` | `WellnessRecord` |
| `Invoice` | `InvoiceRecord` |

The left column shows the exact string to send in API requests. The right column is the NRCES FHIR StructureDefinition profile the backend uses when building the FHIR bundle for data push. `OPDocumentRecord` is not a valid ABDM hiType and will be rejected by the gateway.

Failure when nothing is decrypted:

```json
{
  "errorCode": "INVALID_REQUEST",
  "message": "No decrypted records found for this tracking ID",
  "details": {}
}
```

### 7. Automatic vs Manual HIP Acknowledgements

Some ABDM callbacks require a HIP acknowledgement. In this backend, the callback and data-flow modules automate part of that work, but not every acknowledgement is fully automatic.

| ABDM situation | Backend behavior | Should hospital call manually? |
|---|---|---:|
| ABDM sends callback to `/callback/...` | Backend stores the raw callback, correlates it, updates status, and dispatches customer webhook. | No for storage/correlation. |
| ABDM sends HIP `health-information/request` callback | Backend creates a data-flow job automatically when the callback path contains `health-information/request`. The data-flow worker pushes available records to `dataPushUrl`. | Usually no. Manual call only if automatic job is disabled, failed, or the hospital wants explicit control. |
| HIP health-information data push completes | Data-flow worker tries to notify ABDM if `abdmGatewayToken` is configured. If no gateway token is configured, notify status is `skipped`. | Call manually or fix token configuration if ABDM notify is required and status is `skipped`. |
| ABDM sends consent notification to HIP | Backend can store/correlate the callback and send the customer webhook. The manual endpoint exists to acknowledge the consent notification to ABDM. | Yes if your deployment has not automated this acknowledgement for that callback path. |
| Scan-and-share profile callback | Backend stores/correlates callback. Hospital should acknowledge after accepting the profile and optionally issuing token number. | Yes, call `/v1/share/on-share`. |

Rule of thumb: if the webhook tells the hospital to make a business decision, call the relevant acknowledgement endpoint after that decision. If the data-flow worker has already processed and pushed records, do not call the acknowledgement endpoint again unless support asks you to replay it.

### 8. HIP Consent Notification Acknowledgement

```http
POST <baseUrl>/v1/hip/consent/on-notify
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "consentId": "<consentId>",
  "status": "OK",
  "requestId": "<requestId>"
}
```

| Field | Required | Definition |
|---|---:|---|
| `consentId` | Yes | Consent ID from ABDM consent notification callback. |
| `status` | No | Acknowledgement status. Defaults to `OK`. |
| `requestId` | Yes | Original request ID from ABDM consent notification callback. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

### 9. HIP Health Information Request Acknowledgement

```http
POST <baseUrl>/v1/hip/health-information/on-request
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "transactionId": "<transactionId>",
  "sessionStatus": "ACKNOWLEDGED",
  "requestId": "<requestId>",
  "careContextReferences": ["<careContextReference>"]
}
```

| Field | Required | Definition |
|---|---:|---|
| `transactionId` | Yes | Transaction ID from ABDM health-information request callback. |
| `sessionStatus` | No | Session acknowledgement status. Defaults to `ACKNOWLEDGED`. |
| `requestId` | Yes | Original request ID from ABDM health-information callback. |
| `careContextReferences` | No | Care contexts acknowledged as available. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

### 10. HIP Data Push (M2 — Hospital Encrypts and Pushes Directly)

When a HIU requests health information, ABDM sends `/api/v3/hip/health-information/request` to the HIP webhook. This callback contains:

- `hiRequest.hi.dataPushUrl` — the URL where the hospital must POST encrypted FHIR data
- `hiRequest.keyMaterial` — the HIU's ECDH key material for encryption

The hospital receives this via the **raw ABDM delivery** (`X-Abdm-Path: /api/v3/hip/health-information/request`) and via the **formatted Sahai event** (`eventType: dataFlow.jobCreated`).

The hospital then:

1. Retrieves the care context records using the referenced care context IDs.
2. Builds a FHIR R4 document bundle for each care context.
3. Encrypts each bundle using ABDM M3 ECDH encryption with the HIU `keyMaterial`.
4. POSTs the encrypted entries directly to `dataPushUrl` (not through Sahai).

The `dataPushUrl` is provided by ABDM and is used directly by the hospital — Sahai is not in the push path.

After pushing, call `/v1/hip/health-information/on-request` to acknowledge the health-information request to ABDM.

## Flow 7: Scan and Share

### Acknowledge Patient Profile Share

```http
POST <baseUrl>/v1/share/on-share
Authorization: Bearer <apiKey>
Content-Type: application/json
```

Request body:

```json
{
  "requestId": "<requestId>",
  "status": "SUCCESS",
  "abhaAddress": "<abhaAddress>",
  "tokenNumber": "<tokenNumber>",
  "expiry": "<expiryTimestamp>",
  "context": []
}
```

| Field | Required | Definition |
|---|---:|---|
| `requestId` | Yes | Request ID from ABDM patient-share callback. |
| `status` | No | Acknowledgement status, usually `SUCCESS` or `FAILURE`. Defaults to `SUCCESS`. |
| `abhaAddress` | No | Patient ABHA address from shared profile. |
| `tokenNumber` | No | Hospital token/queue number issued to patient. |
| `expiry` | No | Token expiry timestamp. |
| `context` | No | Additional context sent back to ABDM. |

Success response: Pass-through ABDM gateway response or empty object. See `ABDM Pass-Through Responses`.

## Internal Gateway Routes

These are not customer APIs. External HMS developers can ignore this section unless Sahai support asks them to inspect callback or data-flow delivery.

They are mounted for ABDM callbacks and data flow workers.

| Route | Module | Purpose |
|---|---|---|
| `ANY /callback` | `callbackRouter` | Receives ABDM callbacks. |
| `ANY /callback/{callbackPath}` | `callbackRouter` | Receives nested ABDM callback paths. |
| `POST /data` | `dataFlow` | Receives health data push jobs. |
| `ANY /data/{dataPath}` | `dataFlow` | Receives nested health data/data-flow paths. |
| `POST /internal/data-flow/jobs` | `dataFlow` | Internal data-flow job endpoint. |

## Strict Request Validation

Most request bodies use strict models. Do not send fields not listed in this document unless the endpoint is explicitly marked flexible.

Flexible endpoints:

| API | Reason |
|---|---|
| `POST /v1/user-linking/on-discover` | ABDM user-linking response payloads can vary. |
| `POST /v1/user-linking/on-init` | ABDM user-linking response payloads can vary. |
| `POST /v1/user-linking/on-confirm` | ABDM user-linking response payloads can vary. |
