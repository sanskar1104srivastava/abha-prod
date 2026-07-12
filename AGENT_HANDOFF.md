# Production Backend Agent Handoff

## Context

`production-backend/` is a new clean backend scaffold for Sahai HMS external APIs and ABDM callback/data flows. It is separate from the older `backend/` and `callback/` code and is intended for Docker-image AWS Lambda deployment only.

Fixed deployment defaults:

- AWS profile: `algoflow`
- AWS region: `ap-south-1`
- Package type: Lambda container images, no zip
- Runtime config: AWS Secrets Manager

## What Is Done

- Created the modular folder structure under `production-backend/`.
- Added shared common packages for AWS, config, DynamoDB, HTTP, logging, security, ABDM helpers, and utils.
- Added four Lambda modules:
  - `externalApi`: public `/v1/...` API surface for HMS clients.
  - `callbackRouter`: ABDM callback receiver and correlation router.
  - `dataFlow`: `/data` endpoint and data encryption/decryption flow boundary.
  - `webhookDispatcher`: SQS-driven client webhook sender.
- Added Dockerfiles for all four modules.
- Added `deploy/moduleRegistry.json` as the source of truth for modules, ECR repos, Lambda names, memory, timeout, routes, env vars, dev/prod secret names, and AWS defaults.
- Added `deploy/deploy.ps1` and `deploy/deploy.sh` to build images, push to ECR, and create/update Lambda functions.
- Added `deploy/setup-secrets.ps1` and `deploy/setup-secrets.sh` to create/update environment secrets.
- Added `deploy/secret.schema.json` showing the expected Secrets Manager JSON shape.
- Added Secrets Manager loading in `common/config/settings.py`.
- Removed ABDM base URLs and endpoint paths from application code; they should come from the environment secret.
- Added contract/static tests under `production-backend/tests/`.
- Last verified locally:
  - `python -m unittest discover -s production-backend/tests`
  - `python -m compileall -q production-backend`
  - no hardcoded ABDM URL/path tokens in `common/`, `modules/`, or `deploy/`.

## AWS State

- Dev sandbox secret was created as `sahai/production-backend/dev` in `ap-south-1`.
- Prod secret is not populated yet.
- Dev Lambda deployment was started but interrupted before completion. Do not assume Lambdas/ECR repos/roles are fully created.
- Before resuming deployment, check partial AWS state for:
  - IAM role `sahai-production-backend-dev-lambda-role`
  - ECR repos `sahai-production-*`
  - Lambda functions `sahai-dev-external-api`, `sahai-dev-callback-router`, `sahai-dev-data-flow`, `sahai-dev-webhook-dispatcher`

## What Is Pending

- Recheck partial AWS resources after the interrupted deploy.
- Resume dev deployment with:

```powershell
powershell -ExecutionPolicy Bypass -File production-backend/deploy/deploy.ps1 -Environment dev
```

- Populate `sahai/production-backend/prod` before any prod deploy.
- Add or wire API Gateway provisioning. Current registry lists routes, but the deployment scripts focus on ECR and Lambda creation/update.
- Add or wire DynamoDB, SQS, DLQ, and S3 provisioning. Current registry lists these resources, but creation is not complete yet.
- Connect real API handlers to all M1/M2/M3 endpoints. Current modules are clean scaffolds/contracts, not a full migration of old business logic.
- Extract the full encryption/decryption and ABDM data-flow logic from older files into `dataFlow`.
- Add live integration tests after dev Lambda/API Gateway wiring is complete.

## Important Rules For Next Agent

- Do not put ABDM endpoints or secrets back into code.
- Keep dev/prod values in Secrets Manager only:
  - `sahai/production-backend/dev`
  - `sahai/production-backend/prod`
- Keep `deploy/moduleRegistry.json` as the deployment source of truth.
- Use only container image Lambda deployment APIs:
  - `--package-type Image`
  - `--code ImageUri=...`
- Do not reuse old zip-based callback deployment.
- Do not print client secrets or secret JSON values in logs or chat.

