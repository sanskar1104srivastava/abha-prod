#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_PATH="$SCRIPT_DIR/moduleRegistry.json"

PROFILE=$(python3 -c "import json,sys; d=json.load(open('$REGISTRY_PATH')); print(d['aws']['profile'])")
REGION=$(python3 -c "import json,sys; d=json.load(open('$REGISTRY_PATH')); print(d['aws']['region'])")

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"

ensure_dynamo_table() {
    local TABLE_NAME="$1"
    local ATTR_DEFS="$2"
    local KEY_SCHEMA="$3"
    local GSIJSON="$4"
    local HAS_TTL="${5:-0}"

    if aws dynamodb describe-table --profile "$PROFILE" --region "$REGION" --table-name "$TABLE_NAME" &>/dev/null; then
        echo "  [exists] $TABLE_NAME"
        return
    fi
    local ARGS=(dynamodb create-table
        --profile "$PROFILE" --region "$REGION"
        --table-name "$TABLE_NAME"
        --billing-mode PAY_PER_REQUEST
        --attribute-definitions "$ATTR_DEFS"
        --key-schema "$KEY_SCHEMA"
    )
    if [ "$GSIJSON" != "[]" ]; then
        ARGS+=(--global-secondary-indexes "$GSIJSON")
    fi
    aws "${ARGS[@]}" > /dev/null
    aws dynamodb wait table-exists --profile "$PROFILE" --region "$REGION" --table-name "$TABLE_NAME"
    if [ "$HAS_TTL" -eq 1 ]; then
        aws dynamodb update-time-to-live --profile "$PROFILE" --region "$REGION" \
            --table-name "$TABLE_NAME" \
            --time-to-live-specification "Enabled=true,AttributeName=expiresAt" > /dev/null
    fi
    echo "  [created] $TABLE_NAME"
}

ensure_table_ttl() {
    local TABLE_NAME="$1"
    local TTL_STATUS
    TTL_STATUS=$(aws dynamodb describe-time-to-live --profile "$PROFILE" --region "$REGION" \
        --table-name "$TABLE_NAME" --query TimeToLiveDescription.TimeToLiveStatus --output text 2>/dev/null || echo "NONE")
    if [ "$TTL_STATUS" = "ENABLED" ] || [ "$TTL_STATUS" = "ENABLING" ]; then
        return
    fi
    aws dynamodb update-time-to-live --profile "$PROFILE" --region "$REGION" \
        --table-name "$TABLE_NAME" \
        --time-to-live-specification "Enabled=true,AttributeName=expiresAt" > /dev/null
    echo "  [ttl-enabled] $TABLE_NAME"
}

ensure_sqs_queue() {
    local QUEUE_NAME="$1"
    local DLQ_ARN="${2:-}"
    local EXISTING_URL
    EXISTING_URL=$(aws sqs get-queue-url --profile "$PROFILE" --region "$REGION" \
        --queue-name "$QUEUE_NAME" --query QueueUrl --output text 2>/dev/null || true)
    if [ -n "$EXISTING_URL" ]; then
        echo "  [exists] $QUEUE_NAME"
        echo "$EXISTING_URL"
        return
    fi
    local CREATE_ARGS=(sqs create-queue --profile "$PROFILE" --region "$REGION" --queue-name "$QUEUE_NAME")
    if [ -n "$DLQ_ARN" ]; then
        CREATE_ARGS+=(--attributes "RedrivePolicy={\"deadLetterTargetArn\":\"$DLQ_ARN\",\"maxReceiveCount\":\"3\"}")
    fi
    local RESULT
    RESULT=$(aws "${CREATE_ARGS[@]}")
    echo "  [created] $QUEUE_NAME"
    echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['QueueUrl'])"
}

get_queue_arn() {
    local QUEUE_URL="$1"
    aws sqs get-queue-attributes --profile "$PROFILE" --region "$REGION" \
        --queue-url "$QUEUE_URL" --attribute-names QueueArn \
        --query Attributes.QueueArn --output text
}

ensure_s3_bucket() {
    local BUCKET_NAME="$1"
    if aws s3api head-bucket --profile "$PROFILE" --region "$REGION" --bucket "$BUCKET_NAME" &>/dev/null; then
        echo "  [exists] $BUCKET_NAME"
        return
    fi
    aws s3api create-bucket --profile "$PROFILE" --region "$REGION" --bucket "$BUCKET_NAME" \
        --create-bucket-configuration "LocationConstraint=$REGION" > /dev/null
    aws s3api put-bucket-encryption --profile "$PROFILE" --region "$REGION" --bucket "$BUCKET_NAME" \
        --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' > /dev/null
    aws s3api put-public-access-block --profile "$PROFILE" --region "$REGION" --bucket "$BUCKET_NAME" \
        --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" > /dev/null
    echo "  [created] $BUCKET_NAME"
}

ensure_s3_lifecycle() {
    local BUCKET_NAME="$1"
    local EXPIRE_DAYS="$2"
    aws s3api put-bucket-lifecycle-configuration --profile "$PROFILE" --region "$REGION" --bucket "$BUCKET_NAME" \
        --lifecycle-configuration "{\"Rules\":[{\"ID\":\"expire-health-records\",\"Status\":\"Enabled\",\"Filter\":{\"Prefix\":\"\"},\"Expiration\":{\"Days\":$EXPIRE_DAYS},\"AbortIncompleteMultipartUpload\":{\"DaysAfterInitiation\":7}}]}" > /dev/null
    echo "  [lifecycle] $BUCKET_NAME (objects expire after ${EXPIRE_DAYS}d)"
}

PROJECTION_ALL='"Projection":{"ProjectionType":"ALL"}'
PK_SK_ATTRS='[{"AttributeName":"pk","AttributeType":"S"},{"AttributeName":"sk","AttributeType":"S"}]'
PK_SK_KEY='[{"AttributeName":"pk","KeyType":"HASH"},{"AttributeName":"sk","KeyType":"RANGE"}]'

echo ""
echo "[DynamoDB tables]"

ensure_dynamo_table "sahaiHospitalTenants" "$PK_SK_ATTRS" "$PK_SK_KEY" "[]"
ensure_dynamo_table "sahaiApiKeys" \
    '[{"AttributeName":"apiKeyHash","AttributeType":"S"}]' \
    '[{"AttributeName":"apiKeyHash","KeyType":"HASH"}]' "[]"
ensure_dynamo_table "sahaiPatients" "$PK_SK_ATTRS" "$PK_SK_KEY" "[]"
ensure_dynamo_table "sahaiCareContexts" "$PK_SK_ATTRS" "$PK_SK_KEY" "[]"

REQUEST_LOG_ATTRS='[
  {"AttributeName":"pk","AttributeType":"S"},{"AttributeName":"sk","AttributeType":"S"},
  {"AttributeName":"requestId","AttributeType":"S"},{"AttributeName":"transactionId","AttributeType":"S"},
  {"AttributeName":"consentRequestId","AttributeType":"S"},{"AttributeName":"consentId","AttributeType":"S"},
  {"AttributeName":"hipId","AttributeType":"S"},{"AttributeName":"hiuId","AttributeType":"S"}
]'
REQUEST_LOG_GSIS='[
  {"IndexName":"requestIdIndex","KeySchema":[{"AttributeName":"requestId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},
  {"IndexName":"transactionIdIndex","KeySchema":[{"AttributeName":"transactionId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},
  {"IndexName":"consentRequestIdIndex","KeySchema":[{"AttributeName":"consentRequestId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},
  {"IndexName":"consentIdIndex","KeySchema":[{"AttributeName":"consentId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},
  {"IndexName":"hipIdIndex","KeySchema":[{"AttributeName":"hipId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},
  {"IndexName":"hiuIdIndex","KeySchema":[{"AttributeName":"hiuId","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}
]'
ensure_dynamo_table "sahaiRequestLog" "$REQUEST_LOG_ATTRS" "$PK_SK_KEY" "$REQUEST_LOG_GSIS" 1

STATUS_STORE_ATTRS='[
  {"AttributeName":"pk","AttributeType":"S"},{"AttributeName":"sk","AttributeType":"S"},
  {"AttributeName":"status","AttributeType":"S"},{"AttributeName":"updatedAt","AttributeType":"S"}
]'
STATUS_STORE_GSIS='[
  {"IndexName":"statusUpdatedIndex","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"updatedAt","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}
]'
ensure_dynamo_table "sahaiStatusStore" "$STATUS_STORE_ATTRS" "$PK_SK_KEY" "$STATUS_STORE_GSIS"
ensure_dynamo_table "sahaiWebhookEvents" "$PK_SK_ATTRS" "$PK_SK_KEY" "[]"
ensure_dynamo_table "sahaiHealthRecords" "$PK_SK_ATTRS" "$PK_SK_KEY" "[]" 1
ensure_dynamo_table "abdmCorrelation" \
    '[{"AttributeName":"pk","AttributeType":"S"}]' \
    '[{"AttributeName":"pk","KeyType":"HASH"}]' "[]" 1

# Idempotent TTL enablement — also covers tables created before TTL was added.
# Items without an expiresAt attribute (e.g. access-audit records) are never expired.
ensure_table_ttl "sahaiRequestLog"
ensure_table_ttl "sahaiHealthRecords"
ensure_table_ttl "abdmCorrelation"
ensure_table_ttl "sahaiStatusStore"

echo ""
echo "[SQS queues]"

WEBHOOK_DLQ_URL=$(ensure_sqs_queue "sahaiWebhookEventsDlq" | tail -1)
WEBHOOK_DLQ_ARN=$(get_queue_arn "$WEBHOOK_DLQ_URL")
WEBHOOK_QUEUE_URL=$(ensure_sqs_queue "sahaiWebhookEventsQueue" "$WEBHOOK_DLQ_ARN" | tail -1)

DATAFLOW_DLQ_URL=$(ensure_sqs_queue "sahaiDataFlowJobsDlq" | tail -1)
DATAFLOW_DLQ_ARN=$(get_queue_arn "$DATAFLOW_DLQ_URL")
DATAFLOW_QUEUE_URL=$(ensure_sqs_queue "sahaiDataFlowJobsQueue" "$DATAFLOW_DLQ_ARN" | tail -1)

ABDM_CB_DLQ_URL=$(ensure_sqs_queue "sahaiAbdmCallbacksDlq" | tail -1)
ABDM_CB_DLQ_ARN=$(get_queue_arn "$ABDM_CB_DLQ_URL")
ABDM_CB_QUEUE_URL=$(ensure_sqs_queue "sahaiAbdmCallbacksQueue" "$ABDM_CB_DLQ_ARN" | tail -1)

echo ""
echo "[S3 buckets]"

ensure_s3_bucket "sahai-production-callback-bodies"
ensure_s3_bucket "sahai-production-encrypted-records"
ensure_s3_bucket "sahai-production-decrypted-records"

# Health data must not persist indefinitely — align with the 30-day request TTL.
ensure_s3_lifecycle "sahai-production-encrypted-records" 30
ensure_s3_lifecycle "sahai-production-decrypted-records" 30

echo ""
echo "[Done] Infrastructure provisioned for environment: $ENVIRONMENT"
echo ""
echo "SQS URLs to put in Secrets Manager (sahai/production-backend/$ENVIRONMENT):"
echo "  webhookEventsQueueUrl = $WEBHOOK_QUEUE_URL"
echo "  dataFlowJobsQueueUrl  = $DATAFLOW_QUEUE_URL"
echo ""
echo "Next steps:"
echo "  1. Add SQS URLs to the secret: sahai/production-backend/$ENVIRONMENT"
echo "  2. Run deploy.sh $ENVIRONMENT"
echo "  3. Wire API Gateway routes to Lambda functions"
echo "  4. Add SQS event source mapping: $ABDM_CB_QUEUE_URL → sahai-$ENVIRONMENT-abdm-callback-consumer"
