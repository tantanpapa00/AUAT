# BBooster PC App Build Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\build.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster Production Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if dependencies are installed
if (-not (Test-Path "$PSScriptRoot\..\ui\node_modules")) {
    Write-Host "UI dependencies not found. Run setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Build UI first
Write-Host "[1/2] Building UI..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\ui"
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  UI build failed" -ForegroundColor Red
    exit 1
}
Write-Host "  UI build complete" -ForegroundColor Green

# Build Tauri
Write-Host "[2/2] Building Tauri application..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\src-tauri"
cargo tauri build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Tauri build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output files:" -ForegroundColor Yellow
Write-Host "  - EXE: src-tauri\target\release\BBooster.exe" -ForegroundColor White
Write-Host "  - NSIS Installer: src-tauri\target\release\bundle\nsis\BBooster_*_x64-setup.exe" -ForegroundColor White
Write-Host "  - MSI Package: src-tauri\target\release\bundle\msi\BBooster_*.msi" -ForegroundColor White
Write-Host ""
