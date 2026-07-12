param(
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RegistryPath = Join-Path $ScriptDir "moduleRegistry.json"
$Registry = Get-Content -Raw -LiteralPath $RegistryPath | ConvertFrom-Json
$Profile = $Registry.aws.profile
$Region = $Registry.aws.region
$EnvConfig = $Registry.environments.PSObject.Properties[$Environment].Value
if (-not $EnvConfig) { throw "Unknown environment: $Environment" }

$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region

function Ensure-DynamoTable {
    param([string]$TableName, [array]$AttributeDefs, [array]$KeySchema, [array]$GSIs, [int]$Ttl = 0)
    $SavedEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & aws dynamodb describe-table --profile $Profile --region $Region --table-name $TableName *> $null
    $Exists = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $SavedEAP
    if ($Exists) {
        Write-Host "  [exists] $TableName"
        return
    }
    $Args = @(
        "dynamodb", "create-table",
        "--profile", $Profile, "--region", $Region,
        "--table-name", $TableName,
        "--billing-mode", "PAY_PER_REQUEST"
    )
    $AttrJson = $AttributeDefs | ConvertTo-Json -Compress
    $KeyJson = $KeySchema | ConvertTo-Json -Compress
    $Args += "--attribute-definitions"
    $Args += $AttrJson
    $Args += "--key-schema"
    $Args += $KeyJson
    if ($GSIs -and $GSIs.Count -gt 0) {
        $GsiJson = $GSIs | ConvertTo-Json -Compress -Depth 8
        $Args += "--global-secondary-indexes"
        $Args += $GsiJson
    }
    & aws @Args | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create DynamoDB table $TableName" }
    aws dynamodb wait table-exists --profile $Profile --region $Region --table-name $TableName
    if ($Ttl -gt 0) {
        aws dynamodb update-time-to-live --profile $Profile --region $Region --table-name $TableName --time-to-live-specification "Enabled=true,AttributeName=expiresAt" | Out-Null
    }
    Write-Host "  [created] $TableName"
}

function Ensure-SqsQueue {
    param([string]$QueueName, [string]$DlqArn = "")
    $SavedEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $QueueUrl = aws sqs get-queue-url --profile $Profile --region $Region --queue-name $QueueName --query QueueUrl --output text 2>$null
    $ErrorActionPreference = $SavedEAP
    if ($QueueUrl -and $LASTEXITCODE -eq 0) {
        Write-Host "  [exists] $QueueName"
        return $QueueUrl
    }
    $CreateArgs = @("sqs", "create-queue", "--profile", $Profile, "--region", $Region, "--queue-name", $QueueName)
    if ($DlqArn) {
        $RedrivePolicy = "{`"deadLetterTargetArn`":`"$DlqArn`",`"maxReceiveCount`":`"3`"}"
        $CreateArgs += "--attributes"
        $CreateArgs += "RedrivePolicy=$RedrivePolicy"
    }
    $Result = & aws @CreateArgs | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Failed to create SQS queue $QueueName" }
    Write-Host "  [created] $QueueName"
    return $Result.QueueUrl
}

function Get-QueueArn {
    param([string]$QueueUrl)
    return aws sqs get-queue-attributes --profile $Profile --region $Region --queue-url $QueueUrl --attribute-names QueueArn --query Attributes.QueueArn --output text
}

function Ensure-S3Bucket {
    param([string]$BucketName)
    $SavedEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & aws s3api head-bucket --profile $Profile --region $Region --bucket $BucketName *> $null
    $Exists = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $SavedEAP
    if ($Exists) {
        Write-Host "  [exists] $BucketName"
        return
    }
    aws s3api create-bucket --profile $Profile --region $Region --bucket $BucketName --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create S3 bucket $BucketName" }
    aws s3api put-bucket-encryption --profile $Profile --region $Region --bucket $BucketName `
        --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' | Out-Null
    aws s3api put-public-access-block --profile $Profile --region $Region --bucket $BucketName `
        --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" | Out-Null
    Write-Host "  [created] $BucketName"
}

$Env = $EnvConfig.appEnv
$Prefix = "sahai"

# ── DynamoDB tables ──────────────────────────────────────────────────────────

Write-Host "`n[DynamoDB tables]"

$GsiProjectionAll = @{Projection = @{ProjectionType = "ALL"}}
$GsiKeyHipId     = @{IndexName = "hipIdIndex";    KeySchema = @(@{AttributeName="hipId";KeyType="HASH"});    @GsiProjectionAll}
$GsiKeyHiuId     = @{IndexName = "hiuIdIndex";    KeySchema = @(@{AttributeName="hiuId";KeyType="HASH"});    @GsiProjectionAll}
$GsiRequestId    = @{IndexName = "requestIdIndex"; KeySchema = @(@{AttributeName="requestId";KeyType="HASH"}); @GsiProjectionAll}
$GsiTxnId        = @{IndexName = "transactionIdIndex"; KeySchema = @(@{AttributeName="transactionId";KeyType="HASH"}); @GsiProjectionAll}
$GsiConsentReqId = @{IndexName = "consentRequestIdIndex"; KeySchema = @(@{AttributeName="consentRequestId";KeyType="HASH"}); @GsiProjectionAll}
$GsiConsentId    = @{IndexName = "consentIdIndex"; KeySchema = @(@{AttributeName="consentId";KeyType="HASH"}); @GsiProjectionAll}
$GsiPatientId    = @{IndexName = "patientIdIndex"; KeySchema = @(@{AttributeName="patientId";KeyType="HASH"}); @GsiProjectionAll}
$GsiStatusUpd    = @{IndexName = "statusUpdatedIndex"; KeySchema = @(@{AttributeName="status";KeyType="HASH"}, @{AttributeName="updatedAt";KeyType="RANGE"}); @GsiProjectionAll}

Ensure-DynamoTable `
    -TableName "${Prefix}HospitalTenants" `
    -AttributeDefs @(@{AttributeName="pk";AttributeType="S"}, @{AttributeName="sk";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @()

Ensure-DynamoTable `
    -TableName "${Prefix}ApiKeys" `
    -AttributeDefs @(@{AttributeName="apiKeyHash";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="apiKeyHash";KeyType="HASH"}) `
    -GSIs @()

Ensure-DynamoTable `
    -TableName "${Prefix}Patients" `
    -AttributeDefs @(@{AttributeName="pk";AttributeType="S"}, @{AttributeName="sk";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @()

Ensure-DynamoTable `
    -TableName "${Prefix}CareContexts" `
    -AttributeDefs @(@{AttributeName="pk";AttributeType="S"}, @{AttributeName="sk";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @()

Ensure-DynamoTable `
    -TableName "${Prefix}RequestLog" `
    -AttributeDefs @(
        @{AttributeName="pk";AttributeType="S"},
        @{AttributeName="sk";AttributeType="S"},
        @{AttributeName="requestId";AttributeType="S"},
        @{AttributeName="transactionId";AttributeType="S"},
        @{AttributeName="consentRequestId";AttributeType="S"},
        @{AttributeName="consentId";AttributeType="S"},
        @{AttributeName="hipId";AttributeType="S"},
        @{AttributeName="hiuId";AttributeType="S"}
    ) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @($GsiRequestId, $GsiTxnId, $GsiConsentReqId, $GsiConsentId, $GsiKeyHipId, $GsiKeyHiuId) `
    -Ttl 1

Ensure-DynamoTable `
    -TableName "${Prefix}StatusStore" `
    -AttributeDefs @(
        @{AttributeName="pk";AttributeType="S"},
        @{AttributeName="sk";AttributeType="S"},
        @{AttributeName="status";AttributeType="S"},
        @{AttributeName="updatedAt";AttributeType="S"}
    ) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @($GsiStatusUpd)

Ensure-DynamoTable `
    -TableName "${Prefix}WebhookEvents" `
    -AttributeDefs @(@{AttributeName="pk";AttributeType="S"}, @{AttributeName="sk";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @()

Ensure-DynamoTable `
    -TableName "${Prefix}HealthRecords" `
    -AttributeDefs @(@{AttributeName="pk";AttributeType="S"}, @{AttributeName="sk";AttributeType="S"}) `
    -KeySchema @(@{AttributeName="pk";KeyType="HASH"}, @{AttributeName="sk";KeyType="RANGE"}) `
    -GSIs @()

# ── SQS queues ───────────────────────────────────────────────────────────────

Write-Host "`n[SQS queues]"

$WebhookDlqUrl  = Ensure-SqsQueue -QueueName "${Prefix}WebhookEventsDlq"
$WebhookDlqArn  = Get-QueueArn -QueueUrl $WebhookDlqUrl
$WebhookQueueUrl = Ensure-SqsQueue -QueueName "${Prefix}WebhookEventsQueue" -DlqArn $WebhookDlqArn

$DataFlowDlqUrl  = Ensure-SqsQueue -QueueName "${Prefix}DataFlowJobsDlq"
$DataFlowDlqArn  = Get-QueueArn -QueueUrl $DataFlowDlqUrl
$DataFlowQueueUrl = Ensure-SqsQueue -QueueName "${Prefix}DataFlowJobsQueue" -DlqArn $DataFlowDlqArn

# ── S3 buckets ───────────────────────────────────────────────────────────────

Write-Host "`n[S3 buckets]"

Ensure-S3Bucket -BucketName "sahai-production-callback-bodies"
Ensure-S3Bucket -BucketName "sahai-production-encrypted-records"
Ensure-S3Bucket -BucketName "sahai-production-decrypted-records"

# ── Summary ──────────────────────────────────────────────────────────────────

Write-Host "`n[Done] Infrastructure provisioned for environment: $Environment"
Write-Host ""
Write-Host "SQS URLs to put in Secrets Manager:"
Write-Host "  webhookEventsQueueUrl = $WebhookQueueUrl"
Write-Host "  dataFlowJobsQueueUrl  = $DataFlowQueueUrl"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Add SQS URLs to the secret: sahai/production-backend/$Environment"
Write-Host "  2. Run deploy.ps1 -Environment $Environment"
Write-Host "  3. Wire API Gateway routes to Lambda functions"
