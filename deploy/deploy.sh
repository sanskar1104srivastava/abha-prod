#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_PATH="$SCRIPT_DIR/moduleRegistry.json"
TRUST_POLICY_PATH="$SCRIPT_DIR/iam/lambda-trust-policy.json"
INLINE_POLICY_PATH="$SCRIPT_DIR/iam/lambda-inline-policy.json"
ENVIRONMENT="${ENVIRONMENT:-dev}"
IMAGE_TAG="${IMAGE_TAG:-}"
LAMBDA_ROLE_ARN="${LAMBDA_ROLE_ARN:-}"

read -r PROFILE REGION ENV_APP SECRET_NAME LAMBDA_PREFIX ROLE_NAME DEFAULT_TAG < <(python - "$REGISTRY_PATH" "$ENVIRONMENT" <<'PY' | tr -d '\r'
import json
import sys

registry = json.load(open(sys.argv[1], encoding="utf-8"))
environment = sys.argv[2]
env = registry["environments"][environment]
print(
    registry["aws"]["profile"],
    registry["aws"]["region"],
    env["appEnv"],
    env["secretName"],
    env["lambdaNamePrefix"],
    env["lambdaExecutionRoleName"],
    env["imageTag"],
)
PY
)
if [[ -z "$IMAGE_TAG" ]]; then
    IMAGE_TAG="$DEFAULT_TAG"
fi
export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"

resolve_role_arn() {
    if [[ -n "$LAMBDA_ROLE_ARN" ]]; then
        echo "$LAMBDA_ROLE_ARN"
        return
    fi
    if arn="$(aws iam get-role --profile "$PROFILE" --role-name "$ROLE_NAME" --query Role.Arn --output text 2>/dev/null)"; then
        echo "$arn"
        return
    fi
    aws iam create-role --profile "$PROFILE" --role-name "$ROLE_NAME" --assume-role-policy-document "file://$TRUST_POLICY_PATH" >/dev/null
    aws iam put-role-policy --profile "$PROFILE" --role-name "$ROLE_NAME" --policy-name "$ROLE_NAME-inline" --policy-document "file://$INLINE_POLICY_PATH" >/dev/null
    sleep 10
    aws iam get-role --profile "$PROFILE" --role-name "$ROLE_NAME" --query Role.Arn --output text
}

cd "$ROOT_DIR"

ACCOUNT_ID="$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --query Account --output text)"
ROLE_ARN="$(resolve_role_arn)"
REGISTRY_HOST="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
aws ecr get-login-password --profile "$PROFILE" --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY_HOST"

python - "$REGISTRY_PATH" <<'PY' | tr -d '\r' | while IFS=$'\t' read -r module_name module_path repository lambda_suffix memory timeout env_json; do
import json
import sys

registry = json.load(open(sys.argv[1], encoding="utf-8"))
for module_name, module in registry["modules"].items():
    print(
        module_name,
        module["modulePath"],
        module["ecrRepository"],
        module["lambdaNameSuffix"],
        module["memory"],
        module["timeout"],
        json.dumps(module.get("env", {}), separators=(",", ":")),
        sep="\t",
    )
PY
    function_name="$LAMBDA_PREFIX-$lambda_suffix"
    image_uri="$REGISTRY_HOST/$repository:$IMAGE_TAG"
    aws ecr describe-repositories --profile "$PROFILE" --region "$REGION" --repository-names "$repository" >/dev/null 2>&1 || \
        aws ecr create-repository --profile "$PROFILE" --region "$REGION" --repository-name "$repository" >/dev/null

    docker build --provenance=false --platform linux/amd64 -f "$module_path/Dockerfile" -t "$repository:$IMAGE_TAG" .
    docker tag "$repository:$IMAGE_TAG" "$image_uri"
    docker push "$image_uri"

    env_file="$(mktemp -p "$ROOT_DIR" env_XXXXXX.json)"
    python - "$ENV_APP" "$REGION" "$SECRET_NAME" "$env_json" "$env_file" <<'PY'
import json
import sys

env = {
    "appEnv": sys.argv[1],
    "awsRegion": sys.argv[2],
    "configSecretName": sys.argv[3],
}
env.update(json.loads(sys.argv[4]))
with open(sys.argv[5], "w", encoding="utf-8") as handle:
    json.dump({"Variables": env}, handle, separators=(",", ":"))
PY

    win_env_file="$(cygpath -m "$env_file")"
    if aws lambda get-function --profile "$PROFILE" --region "$REGION" --function-name "$function_name" >/dev/null 2>&1; then
        aws lambda update-function-code --profile "$PROFILE" --region "$REGION" --function-name "$function_name" --image-uri "$image_uri" >/dev/null
        aws lambda wait function-updated --profile "$PROFILE" --region "$REGION" --function-name "$function_name"
        aws lambda update-function-configuration --profile "$PROFILE" --region "$REGION" --function-name "$function_name" --memory-size "$memory" --timeout "$timeout" --environment "file://$win_env_file" >/dev/null
    else
        aws lambda create-function --profile "$PROFILE" --region "$REGION" --function-name "$function_name" --package-type Image --code "ImageUri=$image_uri" --role "$ROLE_ARN" --memory-size "$memory" --timeout "$timeout" --environment "file://$win_env_file" >/dev/null
    fi
    rm -f "$env_file"

    echo "Deployed $function_name from $image_uri using secret $SECRET_NAME"
done
