# Install Rust via winget
# Run: powershell -ExecutionPolicy Bypass -File scripts\install-rust.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Rust Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if already installed
$rustVersion = rustc --version 2>$null
if ($rustVersion) {
    Write-Host "Rust is already installed: $rustVersion" -ForegroundColor Green
    exit 0
}

# Try winget first
Write-Host "Installing Rust via winget..." -ForegroundColor Yellow
winget install Rustlang.Rustup --accept-package-agreements --accept-source-agreements

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Rust installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "IMPORTANT: Please restart your terminal/PowerShell to use Rust." -ForegroundColor Yellow
    Write-Host "Then run: .\scripts\setup.ps1" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "winget installation failed. Please install manually:" -ForegroundColor Red
    Write-Host "1. Go to https://rustup.rs/" -ForegroundColor White
    Write-Host "2. Download and run rustup-init.exe" -ForegroundColor White
    Write-Host "3. Restart terminal after installation" -ForegroundColor White
}
