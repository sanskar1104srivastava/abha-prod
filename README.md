# Production Backend

Clean Dockerized Lambda backend for Sahai external ABDM bridge APIs.

Defaults:

- AWS profile: `algoflow`
- AWS region: `ap-south-1`
- Lambda package type: container image

Modules:

- `externalApi`: public `/v1` API for external HMS callers.
- `callbackRouter`: single ABDM bridge callback entry point at `/callback`.
- `abdmCallbackConsumer`: SQS-driven worker that forwards raw ABDM callback bodies to hospital webhooks with `X-Abdm-Path` / `X-Abdm-Signature` headers.
- `dataFlow`: `/data` endpoint and data-flow worker.
- `webhookDispatcher`: SQS-driven worker that delivers formatted Sahai events to hospital webhooks.

Run static checks:

```powershell
python -m unittest discover -s production-backend/tests
```

Deploy:

```powershell
cd production-backend
powershell -ExecutionPolicy Bypass -File deploy/deploy.ps1
```

No zip packaging is used.
