# BBooster Mobile App APK Build Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1

param(
    [switch]$Debug,
    [switch]$Release,
    [switch]$Clean
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster APK Build v0.1.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "$PSScriptRoot\.."

# Determine build type
$buildType = "release"
if ($Debug) {
    $buildType = "debug"
}

# Clean if requested
if ($Clean) {
    Write-Host "[Clean] Removing previous build artifacts..." -ForegroundColor Yellow
    flutter clean
    Write-Host "  Clean complete" -ForegroundColor Green
    Write-Host ""
}

# Get dependencies
Write-Host "[1/4] Getting dependencies..." -ForegroundColor Yellow
flutter pub get
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to get dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies ready" -ForegroundColor Green

# Run analysis
Write-Host "[2/4] Running code analysis..." -ForegroundColor Yellow
flutter analyze --no-fatal-infos
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Analysis found issues (continuing anyway)" -ForegroundColor Yellow
}
else {
    Write-Host "  Analysis passed" -ForegroundColor Green
}

# Build APK
Write-Host "[3/4] Building $buildType APK..." -ForegroundColor Yellow
if ($buildType -eq "debug") {
    flutter build apk --debug
}
else {
    flutter build apk --release --split-per-abi
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  APK build failed" -ForegroundColor Red
    exit 1
}
Write-Host "  APK build complete" -ForegroundColor Green

# Copy APK to root
Write-Host "[4/4] Copying APK files..." -ForegroundColor Yellow
$version = "0.1.0"
$outputDir = "release"

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

if ($buildType -eq "debug") {
    $source = "build\app\outputs\flutter-apk\app-debug.apk"
    $dest = "$outputDir\BBooster-v$version-debug.apk"
    if (Test-Path $source) {
        Copy-Item $source $dest -Force
        Write-Host "  Copied: $dest" -ForegroundColor Green
    }
}
else {
    # Copy split APKs
    $apkDir = "build\app\outputs\flutter-apk"
    $apks = @(
        @{src = "app-arm64-v8-release.apk"; dest = "BBooster-v$version-arm64.apk"},
        @{src = "app-armeabi-v7a-release.apk"; dest = "BBooster-v$version-arm32.apk"},
        @{src = "app-x86_64-release.apk"; dest = "BBooster-v$version-x64.apk"},
        @{src = "app-release.apk"; dest = "BBooster-v$version-universal.apk"}
    )

    foreach ($apk in $apks) {
        $source = Join-Path $apkDir $apk.src
        $dest = Join-Path $outputDir $apk.dest
        if (Test-Path $source) {
            Copy-Item $source $dest -Force
            $size = [math]::Round((Get-Item $dest).Length / 1MB, 2)
            Write-Host "  $($apk.dest) ($size MB)" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output directory: $outputDir\" -ForegroundColor Yellow
Write-Host ""
Write-Host "  APK Types:" -ForegroundColor White
Write-Host "  - arm64: Modern devices (most phones)" -ForegroundColor Gray
Write-Host "  - arm32: Older devices" -ForegroundColor Gray
Write-Host "  - x64: Emulators/ChromeOS" -ForegroundColor Gray
Write-Host "  - universal: All architectures (larger)" -ForegroundColor Gray
Write-Host ""
