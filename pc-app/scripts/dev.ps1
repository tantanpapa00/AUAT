# BBooster PC App Development Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster Development Mode" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if dependencies are installed
if (-not (Test-Path "$PSScriptRoot\..\ui\node_modules")) {
    Write-Host "UI dependencies not found. Run setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Start Tauri dev
Write-Host "Starting Tauri development server..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

Set-Location "$PSScriptRoot\..\src-tauri"
cargo tauri dev
