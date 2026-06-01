# sign_executable.ps1 - Sign a Windows executable with signtool
# ---------------------------------------------------------------
# This script signs a given .exe file using a code-signing certificate.
# It reads certificate details from environment variables.
#
# Environment Variables:
#   SIGN_CERT_PATH      - Path to the .pfx certificate file
#   SIGN_CERT_PASSWORD  - Password for the certificate
#   SIGN_TIMESTAMP_URL  - Timestamp server URL (default: http://timestamp.digicert.com)
#
# Usage:
#   .\sign_executable.ps1 -FilePath "path\to\file.exe"
#   .\sign_executable.ps1 -FilePath "dist\installer\SalesforceTranslationHandler_Setup_1.5.0.exe"

param(
    [Parameter(Mandatory=$true)]
    [string]$FilePath
)

$ErrorActionPreference = "Stop"

# Validate file exists
if (-not (Test-Path $FilePath)) {
    Write-Error "File not found: $FilePath"
    exit 1
}

# Read configuration from environment variables
$CertPath = $env:SIGN_CERT_PATH
$CertPassword = $env:SIGN_CERT_PASSWORD
$TimestampUrl = $env:SIGN_TIMESTAMP_URL

if (-not $TimestampUrl) {
    $TimestampUrl = "http://timestamp.digicert.com"
}

# Validate certificate path
if (-not $CertPath) {
    Write-Error "SIGN_CERT_PATH environment variable is not set."
    Write-Error "Set it to the path of your .pfx certificate file."
    exit 1
}

if (-not (Test-Path $CertPath)) {
    Write-Error "Certificate file not found: $CertPath"
    exit 1
}

if (-not $CertPassword) {
    Write-Error "SIGN_CERT_PASSWORD environment variable is not set."
    exit 1
}

# Find signtool.exe
$SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $SignTool) {
    # Try common Windows SDK locations
    $sdkPaths = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe",
        "${env:ProgramFiles}\Windows Kits\10\bin\*\x64\signtool.exe"
    )
    foreach ($pattern in $sdkPaths) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object -Descending | Select-Object -First 1
        if ($found) {
            $SignTool = $found.FullName
            break
        }
    }
    if (-not $SignTool) {
        Write-Error "signtool.exe not found. Install the Windows SDK or add signtool to PATH."
        exit 1
    }
} else {
    $SignTool = $SignTool.Source
}

Write-Host "Signing: $FilePath"
Write-Host "Certificate: $CertPath"
Write-Host "Timestamp: $TimestampUrl"
Write-Host "SignTool: $SignTool"
Write-Host ""

# Sign the executable
& $SignTool sign `
    /f "$CertPath" `
    /p "$CertPassword" `
    /t "$TimestampUrl" `
    /fd sha256 `
    /v `
    "$FilePath"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Signing failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Successfully signed: $FilePath"

# Verify the signature
Write-Host ""
Write-Host "Verifying signature..."
& $SignTool verify /pa /v "$FilePath"

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Signature verification returned non-zero exit code. The file may still be properly signed."
}

exit 0
