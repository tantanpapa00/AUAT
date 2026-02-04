# Premium Guard Test Script (Week 14 Day 4)
# SSOT: docs/PREMIUM_ENGINE_SPEC.md §7

Write-Host "=== Premium Guard Test ===" -ForegroundColor Cyan

# 1. Check guard settings
Write-Host "`n[1] GET /api/premium/guards" -ForegroundColor Yellow
try {
    $guards = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/guards' -TimeoutSec 10
    Write-Host "cooldown_sec: $($guards.guards.cooldown_sec)"
    Write-Host "daily_limit: $($guards.guards.daily_limit)"
    Write-Host "tf_block_under_15m: $($guards.guards.tf_block_under_15m)"
    Write-Host "[PASS] Guards endpoint works" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 2. Create first signal (should succeed)
Write-Host "`n[2] First signal creation (should succeed)" -ForegroundColor Yellow
$body1 = @{
    asset_id = 999  # 테스트용 asset_id
    symbol = "TEST-USDT"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "GUARD_TEST_1"
    reason_text = "Guard test signal 1"
    tf = "1h"
} | ConvertTo-Json

try {
    $r1 = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body1 -TimeoutSec 10
    Write-Host "ok: $($r1.ok)"
    Write-Host "signal_id: $($r1.signal_id)"
    if ($r1.ok) {
        Write-Host "[PASS] First signal created" -ForegroundColor Green
    } else {
        Write-Host "[WARN] First signal: $($r1.message)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. Create second signal immediately (should be blocked by cooldown)
Write-Host "`n[3] Second signal (same asset, should be blocked by cooldown)" -ForegroundColor Yellow
$body2 = @{
    asset_id = 999
    symbol = "TEST-USDT"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "GUARD_TEST_2"
    reason_text = "Guard test signal 2 (should be blocked)"
    tf = "1h"
} | ConvertTo-Json

try {
    $r2 = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body2 -TimeoutSec 10
    Write-Host "ok: $($r2.ok)"
    Write-Host "message: $($r2.message)"
    if (-not $r2.ok -and $r2.message -match "cooldown") {
        Write-Host "[PASS] Cooldown guard working" -ForegroundColor Green
    } elseif ($r2.ok) {
        Write-Host "[WARN] Signal created (cooldown may be 0 or asset different)" -ForegroundColor Yellow
    } else {
        Write-Host "[INFO] Blocked by: $($r2.message)" -ForegroundColor Cyan
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Test TF warning with short timeframe (5m)
Write-Host "`n[4] TF Warning test (5m timeframe)" -ForegroundColor Yellow
$body3 = @{
    asset_id = 998  # 다른 asset_id (cooldown 회피)
    symbol = "TF-TEST"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TF_WARN_TEST"
    reason_text = "TF warning test"
    tf = "5m"  # 경고 대상
} | ConvertTo-Json

try {
    $r3 = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body3 -TimeoutSec 10
    Write-Host "ok: $($r3.ok)"
    Write-Host "tf_warning: $($r3.tf_warning)"
    Write-Host "message: $($r3.message)"
    if ($r3.ok -and $r3.tf_warning) {
        Write-Host "[PASS] TF warning triggered but signal created" -ForegroundColor Green
    } elseif (-not $r3.ok -and $r3.message -match "tf_blocked") {
        Write-Host "[PASS] TF blocked (PREMIUM_TF_BLOCK_UNDER=1)" -ForegroundColor Green
    } elseif ($r3.ok) {
        Write-Host "[WARN] Signal created without warning (check tf_warning field)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Test with different asset (no cooldown)
Write-Host "`n[5] Different asset (should succeed, no cooldown)" -ForegroundColor Yellow
$body4 = @{
    asset_id = 997  # 다른 asset_id
    symbol = "OTHER-USDT"
    exchange = "OKX"
    premium_mode = "trend"
    side = "entry"
    action = "buy"
    reason_code = "DIFF_ASSET_TEST"
    reason_text = "Different asset test"
    tf = "1h"
} | ConvertTo-Json

try {
    $r4 = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body4 -TimeoutSec 10
    Write-Host "ok: $($r4.ok)"
    Write-Host "signal_id: $($r4.signal_id)"
    if ($r4.ok) {
        Write-Host "[PASS] Different asset succeeds (cooldown is per-asset)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Blocked: $($r4.message)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 6. Summary
Write-Host "`n=== Guard Test Summary ===" -ForegroundColor Cyan
Write-Host "Cooldown: $($guards.guards.cooldown_sec)s per asset"
Write-Host "Daily limit: $($guards.guards.daily_limit) signals/day/asset"
Write-Host "TF block: $($guards.guards.tf_block_under_15m)"

Write-Host "`n=== Test Complete ===" -ForegroundColor Cyan
