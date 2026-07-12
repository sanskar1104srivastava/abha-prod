#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_PATH="$SCRIPT_DIR/moduleRegistry.json"
ENVIRONMENT="${ENVIRONMENT:-dev}"
SECRET_JSON_PATH="${SECRET_JSON_PATH:?SECRET_JSON_PATH is required}"

read -r PROFILE REGION SECRET_NAME < <(python - "$REGISTRY_PATH" "$ENVIRONMENT" <<'PY'
import json
import sys

registry = json.load(open(sys.argv[1], encoding="utf-8"))
environment = sys.argv[2]
env = registry["environments"][environment]
print(registry["aws"]["profile"], registry["aws"]["region"], env["secretName"])
PY
)

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"

if aws secretsmanager describe-secret --profile "$PROFILE" --region "$REGION" --secret-id "$SECRET_NAME" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --profile "$PROFILE" --region "$REGION" --secret-id "$SECRET_NAME" --secret-string "file://$SECRET_JSON_PATH" >/dev/null
    echo "Updated secret $SECRET_NAME"
else
    aws secretsmanager create-secret --profile "$PROFILE" --region "$REGION" --name "$SECRET_NAME" --secret-string "file://$SECRET_JSON_PATH" >/dev/null
    echo "Created secret $SECRET_NAME"
fi
