# Premium OFF Test (Week 14 Day 3)

Write-Host "=== Premium OFF Test ===" -ForegroundColor Cyan

# 1. Check status
Write-Host "`n[1] GET /api/premium/status" -ForegroundColor Yellow
$status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/status' -TimeoutSec 10
Write-Host "premium_enabled: $($status.premium_enabled)"
if (-not $status.premium_enabled) {
    Write-Host "[PASS] Premium is disabled" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Premium should be disabled" -ForegroundColor Red
    exit 1
}

# 2. Try to create signal (should fail)
Write-Host "`n[2] POST /api/diag/premium-test (should fail)" -ForegroundColor Yellow
$body = @{
    asset_id = 1
    symbol = "BTC-USDT"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TEST_OFF"
    reason_text = "test signal when premium off"
    tf = "1h"
} | ConvertTo-Json

$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10
Write-Host "ok: $($result.ok)"
Write-Host "message: $($result.message)"
if (-not $result.ok -and $result.message -match "disabled") {
    Write-Host "[PASS] Signal creation blocked when Premium OFF" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Signal should be blocked" -ForegroundColor Red
}

# 3. Try to list signals (should fail)
Write-Host "`n[3] GET /api/premium/signals (should fail)" -ForegroundColor Yellow
$signals = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/signals' -TimeoutSec 10
Write-Host "ok: $($signals.ok)"
if (-not $signals.ok -and $signals.code -eq "premium_disabled") {
    Write-Host "[PASS] Signal list blocked when Premium OFF" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Signal list should be blocked" -ForegroundColor Red
}

Write-Host "`n=== Premium OFF Test Complete ===" -ForegroundColor Cyan
