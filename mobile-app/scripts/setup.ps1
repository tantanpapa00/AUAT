# BBooster Mobile App Setup Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster Mobile App Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Flutter
Write-Host "[1/3] Checking Flutter..." -ForegroundColor Yellow
$flutterVersion = flutter --version 2>$null
if ($flutterVersion) {
    Write-Host "  Flutter found" -ForegroundColor Green
    flutter --version | Select-Object -First 1
} else {
    Write-Host "  Flutter not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Flutter:" -ForegroundColor Yellow
    Write-Host "  1. Download from https://flutter.dev/docs/get-started/install" -ForegroundColor White
    Write-Host "  2. Or run: winget install Google.Flutter" -ForegroundColor White
    Write-Host "  3. Add Flutter to PATH" -ForegroundColor White
    Write-Host "  4. Restart terminal and run setup again" -ForegroundColor White
    exit 1
}

# Check Android SDK
Write-Host "[2/3] Checking Android SDK..." -ForegroundColor Yellow
flutter doctor --android-licenses 2>$null | Out-Null
$doctorOutput = flutter doctor 2>&1 | Out-String
if ($doctorOutput -match "Android toolchain") {
    Write-Host "  Android SDK configured" -ForegroundColor Green
} else {
    Write-Host "  Android SDK may not be configured properly" -ForegroundColor Yellow
    Write-Host "  Run 'flutter doctor' for details" -ForegroundColor White
}

# Get dependencies
Write-Host "[3/3] Getting Flutter dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\.."
flutter pub get
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to get dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies installed" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run development: flutter run" -ForegroundColor White
Write-Host "  2. Build APK: .\scripts\build-apk.ps1" -ForegroundColor White
Write-Host ""
