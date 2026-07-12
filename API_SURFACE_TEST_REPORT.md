# Sahai Production Backend API Surface Test Report

Generated on 2026-06-23.

## Scope

This report checks the intended API-centric Sahai ABDM integration surface:

- Customer APIs under `/v1/...` on `sahai-dev-external-api`.
- Operator-only APIs under `/v1/admin/...` plus admin-only `/v1/auth/register`.
- ABDM inbound APIs under `/callback/{proxy+}` and `/data`.
- Postman collections inside `production-backend/`.

The goal is to make the public API simple enough that an external HMS/vendor can integrate with only API keys, request/response contracts, status polling, and signed webhook events.

## Executive Status

| Area | Status | Notes |
| --- | --- | --- |
| Route coverage in code | OK | All requested customer, operator, callback, and data routes are mounted locally. |
| Customer Postman collection | OK with cleanup note | `Sahai_Customer_ABDM_API.postman_collection.json` contains the requested customer surface. |
| Operator Postman collection | OK | `Sahai_Operator_Sandbox_Setup.postman_collection.json` contains admin setup, callback simulator, and negative tests. Keep internal only. |
| Deployed dev API | Failing | Live `/v1/health` and `/v1/auth/me` return HTTP 500. |
| Live failure cause | Confirmed | CloudWatch shows `JSONDecodeError` while parsing Secrets Manager secret `sahai/production-backend/dev`. |
| Local contract tests | OK | `python -m unittest discover -s production-backend/tests` passes 13/13 after cleanup. |
| Static syntax check | OK | 101 Python files parsed with `ast.parse`; 0 syntax errors. |

## Main Live Blocker

The deployed API Gateway base URL in the collections is:

```text
https://4sdj5gmx8g.execute-api.ap-south-1.amazonaws.com
```

Safe live smoke test results:

| Method | Path | Live status | Expected |
| --- | --- | ---: | --- |
| GET | `/v1/health` | 500 | 200 |
| GET | `/v1/auth/me` | 500 | 401 without API key |

CloudWatch for `/aws/lambda/sahai-dev-external-api` shows:

```text
JSONDecodeError: Expecting property name enclosed in double quotes
common/config/settings.py -> json.loads(secretText)
configSecretName = sahai/production-backend/dev
```

So the dev Lambda cannot even import the app because the Secrets Manager value is not valid JSON. Until this is fixed, every `/v1/...` API behind `sahai-dev-external-api` will fail live.

## AWS Deployment Inventory

API Gateway:

| API | Value |
| --- | --- |
| Name | `sahai-dev-api` |
| API ID | `3ti0qo8t8k` |
| Endpoint | `https://4sdj5gmx8g.execute-api.ap-south-1.amazonaws.com` |
| Protocol | HTTP |

Deployed routes:

| Route | Integration |
| --- | --- |
| `ANY /v1/{proxy+}` | `sahai-dev-external-api` |
| `ANY /callback` | `sahai-dev-callback-router` |
| `ANY /callback/{proxy+}` | `sahai-dev-callback-router` |
| `POST /data` | `sahai-dev-data-flow` |
| `ANY /data/{proxy+}` | `sahai-dev-data-flow` |
| `ANY /auth` | `sahai-dev-external-api` |
| `ANY /auth/{proxy+}` | `sahai-dev-external-api` |
| `POST /webhook` | `sahai-dev-webhook-receiver` |
| `ANY /webhook/{proxy+}` | `sahai-dev-webhook-receiver` |

Lambda functions:

| Function | Package | Notes |
| --- | --- | --- |
| `sahai-dev-external-api` | Image | Exists; currently fails during init due invalid secret JSON. |
| `sahai-dev-callback-router` | Image | Exists; uses same config secret. |
| `sahai-dev-data-flow` | Image | Exists; log group was not present during check. |
| `sahai-dev-webhook-dispatcher` | Image | Exists. |
| `sahai-dev-webhook-receiver` | Zip | Extra/legacy route target; not part of the planned Docker-only backend. |

Recommendation: remove or clearly isolate the legacy `/webhook` routes and `sahai-dev-webhook-receiver` if the new webhook dispatcher is the intended path.

## Postman Collection Review

| File | Status | Notes |
| --- | --- | --- |
| `Sahai_Customer_ABDM_API.postman_collection.json` | Good customer handoff base | Contains only `/v1/...` customer APIs. Has repeated status/test calls inside flows, which is fine. |
| `Sahai_Operator_Sandbox_Setup.postman_collection.json` | Good internal setup/test base | Contains admin setup, callback simulator, data simulator, and negative tests. Do not share with customers. |
| `Sahai_HMS_Production_Backend.postman_collection.json` | Duplicate customer collection | Currently mirrors the customer collection. Keep only if you want this as an alias; otherwise remove/rename to avoid confusion. |

## Customer-Facing API Test Result

Local FastAPI probe used valid-shaped bodies but no API key. For protected endpoints, HTTP 401 means the route is mounted and the auth boundary is working.

| Group | Endpoints | Local result | Live result |
| --- | --- | --- | --- |
| Health | `GET /v1/health` | 200 `ok` | 500 due invalid secret JSON |
| Auth profile/key | `GET /v1/auth/me`, `POST /v1/auth/rotate-key` | 401 `Bearer API key is required` | 500 due invalid secret JSON |
| Auth login | `POST /v1/auth/login` | 500 locally because it needs DynamoDB | 500 due invalid secret JSON |
| Webhook management | `PUT /v1/webhook-endpoint`, `POST /v1/webhook-endpoint/test` | 401 without API key | 500 due invalid secret JSON |
| Patient/care context | `POST /v1/patients`, `POST /v1/care-contexts`, `POST /v1/link-token`, `POST /v1/care-contexts/link`, `GET /v1/status/{trackingId}`, `GET /v1/health-records/{trackingId}` | 401 without API key | 500 due invalid secret JSON |
| ABHA identity | All `/v1/abha/...` endpoints from the requested list | 401 without API key | 500 due invalid secret JSON |
| Consent/health information | `POST /v1/consents`, `POST /v1/consents/status`, `POST /v1/consents/fetch`, `POST /v1/health-information` | 401 without API key | 500 due invalid secret JSON |
| HIP linking | `POST /v1/hip/link/fetch-modes`, `POST /v1/hip/link/otp-init`, `POST /v1/hip/link/otp-confirm`, `POST /v1/hip/link/care-context/notify`, `POST /v1/hip/sms-notify` | 401 without API key | 500 due invalid secret JSON |
| HIP responses | `POST /v1/hip/consent/on-notify`, `POST /v1/hip/health-information/on-request` | 401 without API key | 500 due invalid secret JSON |
| User-initiated linking | `POST /v1/user-linking/on-discover`, `POST /v1/user-linking/on-init`, `POST /v1/user-linking/on-confirm` | 401 without API key | 500 due invalid secret JSON |
| Scan and share | `POST /v1/share/on-share` | 401 without API key | 500 due invalid secret JSON |

## Operator-Only API Test Result

These routes are mounted and require an admin key from Secrets Manager.

| Method | Path | Local result | Meaning |
| --- | --- | ---: | --- |
| POST | `/v1/admin/customers` | 503 | `adminKey` not configured locally. |
| POST | `/v1/auth/register` | 503 | Correctly admin-only; do not give this to customers. |
| PATCH | `/v1/admin/bridge/callback-url` | 503 | `adminKey` not configured locally. |
| POST | `/v1/admin/bridge/register-services` | 503 | `adminKey` not configured locally. |
| GET | `/v1/admin/bridge/services` | 503 | `adminKey` not configured locally. |

`deploy/secret.schema.json` now includes these required keys:

```json
{
  "adminKey": "",
  "selfCallbackUrl": "",
  "selfDataEndpointUrl": "",
  "facilityBridgeUrl": ""
}
```

## ABDM Inbound Surface Test Result

| Method | Path | Local result | Notes |
| --- | --- | ---: | --- |
| ANY | `/callback/{proxy+}` | 500 locally with sample body | Route is mounted, but runtime needs DynamoDB/S3/valid config. Avoid live simulator calls until secret is fixed. |
| POST | `/data` | 500 locally with sample body | Route is mounted, but runtime needs DynamoDB/S3/valid config. |
| ANY | `/data/{proxy+}` | 500 locally with sample GET | Route is mounted, but runtime needs DynamoDB/S3/valid config. |

Do not expose these to customers as callable API docs. They are ABDM-owned inbound URLs and operator simulator targets only.

## Code Cleanup Done During This Check

- Changed webhook URL update validation to use `NetworkUtils.validateExternalHttpsUrl(...)` instead of a raw string prefix check.
- Added missing secret schema fields for admin and bridge setup:
  - `adminKey`
  - `selfCallbackUrl`
  - `facilityBridgeUrl`

Validation after cleanup:

```text
python -m unittest discover -s production-backend/tests
Ran 13 tests in 0.079s
OK

AST syntax check
syntax_files_checked = 101
syntax_errors = 0
```

## Required Fixes Before Customer Handoff

1. Rebuild `sahai/production-backend/dev` in Secrets Manager as a valid JSON object.
   - Use `production-backend/deploy/secret.schema.json` as the source shape.
   - Do not paste a PowerShell hashtable or single-quoted pseudo-JSON.

2. Confirm the secret includes:
   - ABDM sandbox base URLs and endpoint paths.
   - `adminKey`.
   - `selfCallbackUrl`.
   - `selfDataEndpointUrl`.
   - `facilityBridgeUrl`.
   - SQS queue URLs.

3. Retest live safe endpoints:
   - `GET /v1/health` should return 200.
   - `GET /v1/auth/me` without API key should return 401.
   - `POST /v1/admin/customers` without admin key should return 401, not 503.

4. Create one sandbox customer with `POST /v1/admin/customers`.

5. Use the generated API key to run authenticated customer smoke tests:
   - `GET /v1/auth/me`
   - `PUT /v1/webhook-endpoint`
   - `POST /v1/patients`
   - `POST /v1/care-contexts`
   - `GET /v1/status/{trackingId}`

6. Only after the above, run ABDM sandbox integration flows:
   - ABHA OTP flow.
   - Link token flow.
   - Care-context link flow.
   - Consent request flow.
   - Health-information request and `/data` flow.

7. Remove or isolate legacy API Gateway routes:
   - `ANY /auth`
   - `ANY /auth/{proxy+}`
   - `POST /webhook`
   - `ANY /webhook/{proxy+}`
   - `sahai-dev-webhook-receiver` Zip Lambda, unless deliberately retained for a separate legacy path.

## Handoff Recommendation

Give customers only:

- `Sahai_Customer_ABDM_API.postman_collection.json`
- A short auth guide explaining `Authorization: Bearer <apiKey>` and `Idempotency-Key`.
- Webhook signature verification docs.
- Status and callback event reference.

Keep internal:

- `Sahai_Operator_Sandbox_Setup.postman_collection.json`
- `/v1/admin/...`
- `/v1/auth/register`
- `/callback/...` simulators
- `/data` simulators
- negative tests
