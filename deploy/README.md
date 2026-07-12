# Production Backend Deployment

`moduleRegistry.json` is the source of truth for module names, ECR repositories, Lambda names, memory, timeout, routes, and environment variables.

Defaults:

- AWS profile: `algoflow`
- AWS region: `ap-south-1`
- Lambda package type: container image
- Runtime config source: AWS Secrets Manager

PowerShell:

```powershell
.\deploy\setup-secrets.ps1 -Environment dev -SecretJsonPath <local-secret-payload.json>
.\deploy\deploy.ps1 -Environment dev
```

Bash:

```bash
SECRET_JSON_PATH=<local-secret-payload.json> ENVIRONMENT=dev bash deploy/setup-secrets.sh
ENVIRONMENT=dev bash deploy/deploy.sh
```

The deploy scripts build each module Dockerfile from the `production-backend` root, push to ECR, create or update the environment execution role when needed, and create or update Lambda functions with `--package-type Image` and `ImageUri`.

Application code does not carry ABDM base URLs or ABDM endpoint paths. Store those values in the environment secret defined by `moduleRegistry.json`.
