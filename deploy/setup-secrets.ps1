param(
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev",
    [Parameter(Mandatory = $true)]
    [string]$SecretJsonPath
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RegistryPath = Join-Path $ScriptDir "moduleRegistry.json"
$Registry = Get-Content -Raw -LiteralPath $RegistryPath | ConvertFrom-Json
$Profile = $Registry.aws.profile
$Region = $Registry.aws.region
$EnvironmentConfig = $Registry.environments.PSObject.Properties[$Environment].Value
if (-not $EnvironmentConfig) { throw "Unknown environment: $Environment" }

$ResolvedSecretJsonPath = Resolve-Path -LiteralPath $SecretJsonPath
$SecretName = $EnvironmentConfig.secretName

$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region

$SavedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& aws secretsmanager describe-secret --profile $Profile --region $Region --secret-id $SecretName *> $null
$DescribeExitCode = $LASTEXITCODE
$ErrorActionPreference = $SavedErrorActionPreference
if ($DescribeExitCode -eq 0) {
    aws secretsmanager put-secret-value --profile $Profile --region $Region --secret-id $SecretName --secret-string "file://$ResolvedSecretJsonPath" | Out-Null
    Write-Host "Updated secret $SecretName"
}
else {
    aws secretsmanager create-secret --profile $Profile --region $Region --name $SecretName --secret-string "file://$ResolvedSecretJsonPath" | Out-Null
    Write-Host "Created secret $SecretName"
}
