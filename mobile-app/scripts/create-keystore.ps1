# BBooster Keystore Generation Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\create-keystore.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster Keystore Generator" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "$PSScriptRoot\.."
$androidDir = "$projectRoot\android"
$keystoreDir = "$androidDir\keystore"

# Create keystore directory
if (-not (Test-Path $keystoreDir)) {
    New-Item -ItemType Directory -Path $keystoreDir | Out-Null
    Write-Host "Created keystore directory" -ForegroundColor Green
}

$keystorePath = "$keystoreDir\bbooster-release.jks"

# Check if keystore already exists
if (Test-Path $keystorePath) {
    Write-Host "Keystore already exists at: $keystorePath" -ForegroundColor Yellow
    $overwrite = Read-Host "Overwrite? (y/N)"
    if ($overwrite -ne "y") {
        Write-Host "Cancelled." -ForegroundColor Gray
        exit 0
    }
}

Write-Host ""
Write-Host "Creating release keystore..." -ForegroundColor Yellow
Write-Host "You will be prompted for passwords and certificate information." -ForegroundColor Gray
Write-Host ""

# Generate keystore using keytool
$keytoolCmd = "keytool"
try {
    & $keytoolCmd -genkey -v `
        -keystore $keystorePath `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000 `
        -alias bbooster

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  Keystore Created Successfully!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Keystore: $keystorePath" -ForegroundColor White
        Write-Host ""
        Write-Host "  Next steps:" -ForegroundColor Yellow
        Write-Host "  1. Copy android\key.properties.example to android\key.properties" -ForegroundColor White
        Write-Host "  2. Fill in your passwords in key.properties" -ForegroundColor White
        Write-Host "  3. Run build script: .\scripts\build-apk.ps1" -ForegroundColor White
        Write-Host ""
        Write-Host "  IMPORTANT: Never commit key.properties or .jks files!" -ForegroundColor Red
    }
}
catch {
    Write-Host ""
    Write-Host "keytool not found. Make sure Java JDK is installed and in PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Java JDK:" -ForegroundColor Yellow
    Write-Host "  winget install Oracle.JDK.17" -ForegroundColor White
    Write-Host ""
    Write-Host "Or download from:" -ForegroundColor Yellow
    Write-Host "  https://adoptium.net/" -ForegroundColor White
}
