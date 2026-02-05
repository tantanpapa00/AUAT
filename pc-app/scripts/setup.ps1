# BBooster PC App Setup Script
# Run: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BBooster PC App Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Node.js
Write-Host "[1/4] Checking Node.js..." -ForegroundColor Yellow
$nodeVersion = node --version 2>$null
if ($nodeVersion) {
    Write-Host "  Node.js: $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "  Node.js not found. Please install from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# Check Rust
Write-Host "[2/4] Checking Rust..." -ForegroundColor Yellow
$rustVersion = rustc --version 2>$null
if ($rustVersion) {
    Write-Host "  Rust: $rustVersion" -ForegroundColor Green
} else {
    Write-Host "  Rust not found. Installing via rustup..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Please run the following command manually:" -ForegroundColor Cyan
    Write-Host "  winget install Rustlang.Rustup" -ForegroundColor White
    Write-Host ""
    Write-Host "  Or download from: https://rustup.rs/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  After installation, restart this terminal and run setup again." -ForegroundColor Yellow
    exit 1
}

# Install UI dependencies
Write-Host "[3/4] Installing UI dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\ui"
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to install UI dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  UI dependencies installed" -ForegroundColor Green

# Build Rust dependencies
Write-Host "[4/4] Building Rust dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\src-tauri"
cargo build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to build Rust dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  Rust dependencies built" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run development: .\scripts\dev.ps1" -ForegroundColor White
Write-Host "  2. Build release:   .\scripts\build.ps1" -ForegroundColor White
Write-Host ""
