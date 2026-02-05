# TF Block Test (PREMIUM_TF_BLOCK_UNDER=1)

Write-Host "=== TF Block Test ===" -ForegroundColor Cyan

# Check guards
$guards = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/guards' -TimeoutSec 10
Write-Host "tf_block_under_15m: $($guards.guards.tf_block_under_15m)"

if (-not $guards.guards.tf_block_under_15m) {
    Write-Host "[SKIP] TF block is disabled (PREMIUM_TF_BLOCK_UNDER=0)" -ForegroundColor Yellow
    exit 0
}

# Try to create signal with 5m TF (should be blocked)
Write-Host "`nTrying to create signal with 5m TF..." -ForegroundColor Yellow
$body = @{
    asset_id = 996
    symbol = "BLOCK-TEST"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TF_BLOCK_TEST"
    reason_text = "TF block test"
    tf = "5m"
} | ConvertTo-Json

$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10
Write-Host "ok: $($r.ok)"
Write-Host "message: $($r.message)"

if (-not $r.ok -and $r.message -match "tf_blocked") {
    Write-Host "[PASS] TF < 15m signal blocked" -ForegroundColor Green
} else {
    Write-Host "[FAIL] TF block not working" -ForegroundColor Red
}

# Try with 15m (should succeed)
Write-Host "`nTrying to create signal with 15m TF..." -ForegroundColor Yellow
$body2 = @{
    asset_id = 995
    symbol = "OK-TEST"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TF_OK_TEST"
    reason_text = "15m TF test"
    tf = "15m"
} | ConvertTo-Json

$r2 = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body2 -TimeoutSec 10
Write-Host "ok: $($r2.ok)"
Write-Host "signal_id: $($r2.signal_id)"

if ($r2.ok) {
    Write-Host "[PASS] 15m TF signal created" -ForegroundColor Green
} else {
    Write-Host "[FAIL] 15m should be allowed" -ForegroundColor Red
}

Write-Host "`n=== TF Block Test Complete ===" -ForegroundColor Cyan
