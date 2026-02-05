# BBooster Mobile App APK Build Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster APK Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "$PSScriptRoot\.."

# Clean previous build
Write-Host "[1/3] Cleaning previous build..." -ForegroundColor Yellow
flutter clean
Write-Host "  Clean complete" -ForegroundColor Green

# Get dependencies
Write-Host "[2/3] Getting dependencies..." -ForegroundColor Yellow
flutter pub get
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to get dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies ready" -ForegroundColor Green

# Build APK
Write-Host "[3/3] Building release APK..." -ForegroundColor Yellow
flutter build apk --release
if ($LASTEXITCODE -ne 0) {
    Write-Host "  APK build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  APK Location:" -ForegroundColor Yellow
Write-Host "  build\app\outputs\flutter-apk\app-release.apk" -ForegroundColor White
Write-Host ""

# Copy to more accessible location
$apkSource = "build\app\outputs\flutter-apk\app-release.apk"
$apkDest = "BBooster-v0.1.0.apk"
if (Test-Path $apkSource) {
    Copy-Item $apkSource $apkDest -Force
    Write-Host "  Copied to: $apkDest" -ForegroundColor Green
}
Write-Host ""
