param(
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev",
    [string]$LambdaRoleArn = $env:LAMBDA_ROLE_ARN,
    [string]$ImageTag = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$RegistryPath = Join-Path $ScriptDir "moduleRegistry.json"
$TrustPolicyPath = Join-Path $ScriptDir "iam/lambda-trust-policy.json"
$InlinePolicyPath = Join-Path $ScriptDir "iam/lambda-inline-policy.json"
$Registry = Get-Content -Raw -LiteralPath $RegistryPath | ConvertFrom-Json
$Profile = $Registry.aws.profile
$Region = $Registry.aws.region
$EnvironmentConfig = $Registry.environments.PSObject.Properties[$Environment].Value
if (-not $EnvironmentConfig) { throw "Unknown environment: $Environment" }
if (-not $ImageTag) { $ImageTag = $EnvironmentConfig.imageTag }

$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region

function Resolve-LambdaRoleArn {
    param([string]$ProvidedArn, [string]$RoleName)
    if ($ProvidedArn) { return $ProvidedArn }
    $SavedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $ExistingArn = aws iam get-role --profile $Profile --role-name $RoleName --query Role.Arn --output text 2>$null
    $GetRoleExitCode = $LASTEXITCODE
    $ErrorActionPreference = $SavedErrorActionPreference
    if ($GetRoleExitCode -eq 0 -and $ExistingArn) { return $ExistingArn }
    aws iam create-role --profile $Profile --role-name $RoleName --assume-role-policy-document "file://$TrustPolicyPath" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create IAM role $RoleName" }
    aws iam put-role-policy --profile $Profile --role-name $RoleName --policy-name "$RoleName-inline" --policy-document "file://$InlinePolicyPath" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to attach inline policy to $RoleName" }
    Start-Sleep -Seconds 10
    return aws iam get-role --profile $Profile --role-name $RoleName --query Role.Arn --output text
}

function Write-EnvironmentFile {
    param([hashtable]$Variables)
    $Path = Join-Path ([System.IO.Path]::GetTempPath()) "sahai-lambda-env-$Environment.json"
    @{ Variables = $Variables } | ConvertTo-Json -Compress -Depth 8 | Set-Content -LiteralPath $Path -Encoding ASCII
    return $Path
}

Set-Location $RootDir

$AccountId = aws sts get-caller-identity --profile $Profile --region $Region --query Account --output text
if ($LASTEXITCODE -ne 0) { throw "Unable to resolve AWS account for profile $Profile in $Region" }

$ResolvedRoleArn = Resolve-LambdaRoleArn -ProvidedArn $LambdaRoleArn -RoleName $EnvironmentConfig.lambdaExecutionRoleName
$RegistryHost = "$AccountId.dkr.ecr.$Region.amazonaws.com"
aws ecr get-login-password --profile $Profile --region $Region | docker login --username AWS --password-stdin $RegistryHost
if ($LASTEXITCODE -ne 0) { throw "Docker login to ECR failed" }

foreach ($ModuleProperty in $Registry.modules.PSObject.Properties) {
    $ModuleName = $ModuleProperty.Name
    $Module = $ModuleProperty.Value
    $Repository = $Module.ecrRepository
    $FunctionName = "$($EnvironmentConfig.lambdaNamePrefix)-$($Module.lambdaNameSuffix)"
    $ImageUri = "$RegistryHost/${Repository}:$ImageTag"
    $Dockerfile = Join-Path $Module.modulePath "Dockerfile"

    $SavedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & aws ecr describe-repositories --profile $Profile --region $Region --repository-names $Repository *> $null
    $EcrDescribeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $SavedErrorActionPreference
    if ($EcrDescribeExitCode -ne 0) {
        aws ecr create-repository --profile $Profile --region $Region --repository-name $Repository | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Unable to create ECR repository $Repository" }
    }

    docker build --platform linux/amd64 --provenance=false -f $Dockerfile -t "${Repository}:$ImageTag" .
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed for $ModuleName" }

    docker tag "${Repository}:$ImageTag" $ImageUri
    docker push $ImageUri
    if ($LASTEXITCODE -ne 0) { throw "Docker push failed for $ModuleName" }

    $EnvVars = @{
        appEnv = $EnvironmentConfig.appEnv
        awsRegion = $Region
        configSecretName = $EnvironmentConfig.secretName
    }
    foreach ($EnvProperty in $Module.env.PSObject.Properties) {
        $EnvVars[$EnvProperty.Name] = [string]$EnvProperty.Value
    }
    $EnvFile = Write-EnvironmentFile -Variables $EnvVars

    $SavedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & aws lambda get-function --profile $Profile --region $Region --function-name $FunctionName *> $null
    $LambdaGetExitCode = $LASTEXITCODE
    $ErrorActionPreference = $SavedErrorActionPreference
    if ($LambdaGetExitCode -eq 0) {
        aws lambda update-function-code --profile $Profile --region $Region --function-name $FunctionName --image-uri $ImageUri | Out-Null
        aws lambda wait function-updated --profile $Profile --region $Region --function-name $FunctionName
        aws lambda update-function-configuration --profile $Profile --region $Region --function-name $FunctionName --memory-size $Module.memory --timeout $Module.timeout --environment "file://$EnvFile" | Out-Null
    }
    else {
        aws lambda create-function --profile $Profile --region $Region --function-name $FunctionName --package-type Image --code ImageUri=$ImageUri --role $ResolvedRoleArn --memory-size $Module.memory --timeout $Module.timeout --environment "file://$EnvFile" | Out-Null
    }

    Write-Host "Deployed $FunctionName from $ImageUri using secret $($EnvironmentConfig.secretName)"
}
