# Current HIMS Portal API Inventory

## Scope

This file documents the APIs currently used by `hims-portal/` against the existing backend outside `production-backend/`.

Primary source:

- Frontend API client: `hims-portal/src/api/endpoints.ts`
- HTTP client/base URL: `hims-portal/src/api/client.ts`
- Backend routes: `backend/main.py` and `backend/hims_routes.py`

This is not the new `production-backend` Lambda API list. It is the current working portal surface used by the HIMS portal.

## System Prerequisites

| Requirement | Why the portal needs it |
| --- | --- |
| Existing `abha-backend` / `backend/main.py` deployed | All portal calls go to the current monolithic FastAPI backend. |
| `hims_routes.py` mounted at `/api/hims/*` | Provides local HIMS patient, appointment, user, HIP config, care-context, link-token, and HIP inbox APIs. |
| `VITE_API_BASE` or default API Gateway URL | `hims-portal/src/api/client.ts` sends requests to this backend root. |
| Cookie session and CSRF token | Portal auth uses HttpOnly session cookie plus `X-CSRF-Token` for unsafe methods. |
| Tenant HIP config | Care-context creation/linking requires configured HIP id/name. |
| Callback Lambda/table | HIP inbox, consent status, and health-info request screens depend on callbacks stored by the callback flow. |
| ABDM gateway/session config | ABHA, HIP linking, bridge setup, consent, and data-transfer proxy calls depend on backend ABDM config. |

## Auth And Session

| Portal API | Backend owner | What it does | Classification |
| --- | --- | --- | --- |
| `POST /auth/login` | `backend/main.py` | Logs a portal user in, sets secure session cookies, returns CSRF token. | System prerequisite |
| `POST /auth/logout` | `backend/main.py` | Clears active session and cookies. | System |
| `POST /auth/refresh` | `backend/main.py` | Renews current portal session and CSRF token. | System |
| `GET /auth/me` | `backend/main.py` | Reads authenticated user/client from session. | System |
| `GET /api/hims/me` | `backend/hims_routes.py` | Returns HIMS user, tenant, role, and CSRF token for portal context. | System prerequisite |

## Local HIMS Workflow APIs

These are internal portal/HMS APIs, not ABDM APIs. They are the local operational data layer the portal uses before and around ABDM flows.

| Portal API | Backend owner | What it does | Classification |
| --- | --- | --- | --- |
| `GET /api/hims/dashboard` | `backend/hims_routes.py` | Returns dashboard counters and operational summary. | Portal internal |
| `GET /api/hims/patients` | `backend/hims_routes.py` | Lists local patients for the tenant. | M1 prerequisite |
| `GET /api/hims/patients/search` | `backend/hims_routes.py` | Searches local patients by text or ABHA number. | M1 prerequisite |
| `GET /api/hims/patients/{patient_id}` | `backend/hims_routes.py` | Loads one local patient. | M1 prerequisite |
| `POST /api/hims/patients` | `backend/hims_routes.py` | Creates or merges a local HIMS patient row. | M1 |
| `PATCH /api/hims/patients/{patient_id}` | `backend/hims_routes.py` | Updates canonical patient fields such as ABHA address/number, DOB, mobile. | M1 |
| `GET /api/hims/appointments` | `backend/hims_routes.py` | Lists appointments by tenant/date. | Portal internal |
| `POST /api/hims/appointments` | `backend/hims_routes.py` | Creates an appointment for a local patient. | Portal internal |
| `PATCH /api/hims/appointments/{appointment_id}` | `backend/hims_routes.py` | Updates appointment status/notes. | Portal internal |
| `GET /api/hims/staff` | `backend/hims_routes.py` | Lists staff role rows. | Portal admin |
| `POST /api/hims/staff/role` | `backend/hims_routes.py` | Assigns a portal role to a user. | Portal admin |
| `GET /api/hims/audit` | `backend/hims_routes.py` | Reads tenant audit events. | Portal admin |
| `GET /api/hims/users` | `backend/hims_routes.py` | Lists portal login users. | Portal admin |
| `POST /api/hims/users` | `backend/hims_routes.py` | Creates a portal login user and role. | Portal admin |
| `PATCH /api/hims/users/{username}` | `backend/hims_routes.py` | Updates portal user profile, password, role, or active status. | Portal admin |
| `DELETE /api/hims/users/{username}` | `backend/hims_routes.py` | Deletes/deactivates a portal user. | Portal admin |
| `POST /api/hims/users/me/change-password` | `backend/hims_routes.py` | Lets current portal user change password. | Portal internal |
| `GET /api/hims/hip-config` | `backend/hims_routes.py` | Reads tenant HIP id/name configuration. | M2/M3 prerequisite |
| `PUT /api/hims/hip-config` | `backend/hims_routes.py` | Saves tenant HIP id/name configuration. | M2/M3 prerequisite |

## M1 - ABHA And Patient Setup Used By Portal

These are portal-facing backend wrappers around ABHA/account flows plus local patient mapping.

| Portal API | Backend owner | What it does | Needed before |
| --- | --- | --- | --- |
| `POST /api/enrol/aadhaar/send-otp` | `backend/main.py` | Starts Aadhaar ABHA enrollment OTP. | ABHA creation |
| `POST /api/enrol/aadhaar/verify-otp` | `backend/main.py` | Verifies Aadhaar OTP and proceeds with ABHA enrollment. | ABHA creation |
| `POST /api/enrol/mobile/send-otp` | `backend/main.py` | Sends mobile OTP during ABHA enrollment/update. | ABHA creation |
| `POST /api/enrol/mobile/verify-otp` | `backend/main.py` | Verifies mobile OTP for ABHA enrollment/update. | ABHA creation |
| `POST /api/enrol/abha-address/suggestions` | `backend/main.py` | Gets ABHA address suggestions for an enrollment session. | ABHA address setup |
| `POST /api/enrol/abha-address/set` | `backend/main.py` | Sets chosen ABHA address. | ABHA address setup |
| `POST /api/enrol/dl/send-otp` | `backend/main.py` | Starts DL-based ABHA enrollment OTP. | Optional ABHA creation |
| `POST /api/enrol/dl/verify-otp` | `backend/main.py` | Verifies DL enrollment OTP. | Optional ABHA creation |
| `POST /api/enrol/dl/create` | `backend/main.py` | Completes DL-based ABHA creation. | Optional ABHA creation |
| `POST /api/login/find-by-mobile` | `backend/main.py` | Finds ABHA profiles by mobile. | Patient ABHA mapping |
| `POST /api/phr/search-by-abha` | `backend/main.py` | Searches PHR/ABHA by ABHA number. | Patient ABHA mapping |
| `POST /api/phr/search` | `backend/main.py` | Searches PHR/ABHA by ABHA address. | Patient ABHA mapping |
| `POST /api/hims/patients` | `backend/hims_routes.py` | Stores the patient in HIMS after ABHA creation/lookup or manual entry. | M2/M3 |
| `PATCH /api/hims/patients/{patient_id}` | `backend/hims_routes.py` | Repairs or enriches patient ABHA fields used by portal visibility. | M2/M3 |

## M1 Support - Patient ABHA Login/Profile APIs

The portal uses these when a patient ABHA session is needed for profile/card/QR/update flows.

| Portal API | Backend owner | What it does | Classification |
| --- | --- | --- | --- |
| `POST /api/login/send-otp` | `backend/main.py` | Starts patient ABHA login/verification OTP. | M1 support |
| `POST /api/login/verify-otp` | `backend/main.py` | Verifies patient ABHA login OTP. | M1 support |
| `POST /api/login/x-token` | `backend/main.py` | Exchanges login token/session for patient `x_token`. | M1 support |
| `POST /api/profile/details` | `backend/main.py` | Fetches patient ABHA profile using `x_token`. | M1 support |
| `POST /api/profile/abha-card` | `backend/main.py` | Downloads ABHA card blob. | M1 support |
| `POST /api/profile/qr-code` | `backend/main.py` | Downloads ABHA QR code blob. | M1 support |
| `POST /api/profile/update/email/send-otp` | `backend/main.py` | Sends email update OTP. | M1 support |
| `POST /api/profile/update/email/verify-otp` | `backend/main.py` | Verifies email update OTP. | M1 support |
| `POST /api/profile/update/mobile/send-otp` | `backend/main.py` | Sends mobile update OTP. | M1 support |
| `POST /api/profile/update/mobile/verify-otp` | `backend/main.py` | Verifies mobile update OTP. | M1 support |
| `POST /api/phr/send-otp` | `backend/main.py` | Starts PHR login OTP by ABHA address. | M1 support |
| `POST /api/phr/verify-otp` | `backend/main.py` | Verifies PHR login OTP. | M1 support |
| `POST /api/phr/profile` | `backend/main.py` | Fetches PHR profile. | M1 support |
| `POST /api/phr/card` | `backend/main.py` | Downloads PHR card blob. | M1 support |

## M2 - Care Context And HIP Linking APIs

These are the current portal APIs for care-context creation, token caching, and linking.

| Portal API | Backend owner | What it does | Needed before |
| --- | --- | --- | --- |
| `GET /api/hims/care-contexts` | `backend/hims_routes.py` | Lists local care contexts, optionally by patient. | Linking/data push |
| `POST /api/hims/care-contexts` | `backend/hims_routes.py` | Creates local care context and stores clinical payload/FHIR input shell. | Link care context |
| `GET /api/hims/care-contexts/{cc_id}` | `backend/hims_routes.py` | Loads one care context. | Link/update/data push |
| `PATCH /api/hims/care-contexts/{cc_id}` | `backend/hims_routes.py` | Updates care context, marks linked, stores clinical payload changes. | Data push |
| `GET /api/hims/link-tokens` | `backend/hims_routes.py` | Reads cached link token by HIP and ABHA address. | Link care context |
| `POST /api/hims/link-tokens` | `backend/hims_routes.py` | Stores link token after generate-token flow. | Link care context |
| `POST /api/hip/link/fetch-modes` | `backend/main.py` | Fetches patient auth modes for HIP linking. | Link token/OTP linking |
| `POST /api/hip/link/generate-token` | `backend/main.py` | Generates ABDM link token for a patient/HIP. | Link care context |
| `POST /api/hip/link/otp-init` | `backend/main.py` | Starts OTP auth for link flow. | Link care context |
| `POST /api/hip/link/otp-confirm` | `backend/main.py` | Confirms OTP auth for link flow. | Link care context |
| `POST /api/hip/link/care-context` | `backend/main.py` | Sends care-context link request. Requires `link_token`; does not auto-fetch token. | Portal-visible linked context |
| `POST /api/hip/sms-notify` | `backend/main.py` | Sends deep-link SMS to patient for care-context linking. | Optional linking aid |
| `GET /api/hims/hip/discovery-requests` | `backend/hims_routes.py` | Shows patient discovery callbacks received from ABDM. | User-initiated linking |
| `POST /api/user-linking/on-discovery` | `backend/main.py` | Portal response to patient discovery with matched care contexts. | User-initiated linking |

Important current behavior:

- `POST /api/hims/care-contexts` is local-first storage.
- Save-and-Link in the portal does: cached token lookup -> optional `/api/hip/link/generate-token` -> `/api/hims/link-tokens` -> `/api/hip/link/care-context` -> mark local care context linked.
- `/api/hip/link/care-context` expects `link_token` in the request body and forwards it as `X-LINK-TOKEN`.

**Valid ABDM hiType values (confirmed against ABDM sandbox):**
`OPConsultation`, `DiagnosticReport`, `DischargeSummary`, `Prescription`, `ImmunizationRecord`, `HealthDocumentRecord`, `WellnessRecord`, `Invoice`.
`OPDocumentRecord` is NOT a valid ABDM hiType and will be rejected. When using the production-backend (`POST /v1/care-contexts/link`), pass these exact values in `careContexts[].hiTypes`.

**For production-backend (M2 HIP linking), the canonical flow via `POST /v1/care-contexts/link`:**
1. Call `POST /v1/link-token` → receive link token via webhook (`X-Abdm-Path: /api/v3/token/on-generate-token`).
2. Call `POST /v1/care-contexts/link` with the token and `clinicalPayload: {}` (can be empty at link time; populate before M3 data push).
3. ABDM fires `/api/v3/link/on_carecontext` callback; hospital webhook receives raw body + formatted Sahai event.
4. ABDM auto-fires consent.granted for newly linked care context.

## M3 - Consent, Health Records, And Data Flow APIs

These support HIU consent/data pull and HIP-side data push from the current portal.

| Portal API | Backend owner | What it does | Needed before |
| --- | --- | --- | --- |
| `POST /api/consent/init` | `backend/main.py` | Starts HIU consent request. | Health information pull |
| `POST /api/consent/status` | `backend/main.py` | Checks consent request status. | Consent management |
| `GET /api/consent/requests` | `backend/main.py` | Lists tenant consent-management rows. | Portal consent page |
| `GET /api/consent/artefacts` | `backend/main.py` | Lists granted consent artefacts. | Health record pull |
| `POST /api/consent/pull-records` | `backend/main.py` | Requests/pulls records for consent artefacts. | Health records |
| `POST /api/health-records/process` | `backend/main.py` | Processes/decrypts health records after data arrival. | Record display |
| `GET /api/health-records` | `backend/main.py` | Lists decrypted health records by consent/patient/facility filters. | Portal health records |
| `GET /api/health-records/{record_id}` | `backend/main.py` | Reads one health record. | Portal health records |
| `GET /api/hims/hip/consent-notifications` | `backend/hims_routes.py` | Shows HIP consent notifications received via callbacks. | HIP-side data sharing |
| `GET /api/hims/hip/health-info-requests` | `backend/hims_routes.py` | Shows HIP health-information requests received via callbacks. | HIP-side data sharing |
| `POST /api/data-transfer/build-and-push` | `backend/main.py` | Builds FHIR/PDF payload from care context and pushes to requester. | HIP-side data sharing |
| `POST /api/data-transfer/auto-push-pending` | `backend/main.py` | Auto-pushes pending HIP-side health-info requests. | HIP-side data sharing |
| `POST /api/data-transfer/encrypt-and-push` | `backend/main.py` | Encrypts provided FHIR bundle and pushes it to ABDM data push URL. | HIP-side data sharing |
| `POST /api/data-transfer/data-push` | `backend/main.py` | Low-level/deprecated data-push helper for prebuilt data. | Legacy data transfer |

## Bridge, Facility, And Directory Support

| Portal API | Backend owner | What it does | Classification |
| --- | --- | --- | --- |
| `PATCH /api/bridge/url` | `backend/main.py` | Registers/updates backend callback URL with bridge. | M2/M3 prerequisite |
| `POST /api/bridge/register` | `backend/main.py` | Registers bridge services/facility HRP details. | M2/M3 prerequisite |
| `GET /api/bridge/services` | `backend/main.py` | Lists bridge services for setup validation. | Setup validation |
| `POST /api/hfr/facility/search` | `backend/main.py` | Searches HFR facility directory. | Directory/support |

## Scan And Share

These are used by the portal scan/share patient intake flow.

| Portal API | Backend owner | What it does | Classification |
| --- | --- | --- | --- |
| `POST /api/hip/share/profile` | `backend/main.py` | Starts/handles profile share call. | Patient intake |
| `GET /api/hip/share/list` | `backend/main.py` | Lists scan/share callbacks and auto-acks when possible. | Patient intake |
| `POST /api/hip/share/on-share` | `backend/main.py` | Sends on-share acknowledgement. | Patient intake |
| `DELETE /api/hip/share/{callback_id}` | `backend/main.py` | Removes a handled scan/share callback row. | Patient intake |

## Current Portal Flow Order

1. System login:
   - `POST /auth/login`
   - `GET /api/hims/me`
2. Configure tenant/HIP if not already done:
   - `GET /api/hims/hip-config`
   - `PUT /api/hims/hip-config`
   - `PATCH /api/bridge/url`
   - `POST /api/bridge/register`
3. M1 patient setup:
   - ABHA enrollment/lookup APIs as needed.
   - `POST /api/hims/patients`
   - `PATCH /api/hims/patients/{patient_id}` if canonical ABHA fields need repair.
4. M2 care-context/linking:
   - `POST /api/hims/care-contexts`
   - link-token cache/generate-token APIs
   - `POST /api/hip/link/care-context`
   - `PATCH /api/hims/care-contexts/{cc_id}` to mark linked.
5. M3 consent/records:
   - `POST /api/consent/init`
   - callback-driven consent artefacts
   - `POST /api/consent/pull-records`
   - `GET /api/health-records`
6. HIP-side data sharing:
   - monitor `/api/hims/hip/*` inbox endpoints
   - push records with `/api/data-transfer/build-and-push` or `/api/data-transfer/auto-push-pending`

