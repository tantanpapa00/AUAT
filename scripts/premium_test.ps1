# Premium Engine Test Script (Week 14 Day 3)
# SSOT: docs/PREMIUM_ENGINE_SPEC.md

Write-Host "=== Premium Engine Test ===" -ForegroundColor Cyan

# 1. Premium status
Write-Host "`n[1] GET /api/premium/status" -ForegroundColor Yellow
try {
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/status' -TimeoutSec 10
    Write-Host "premium_enabled: $($status.premium_enabled)"
    Write-Host "available_modes: $($status.available_modes -join ', ')"
    Write-Host "mode_status: trend=$($status.mode_status.trend), mr=$($status.mode_status.mr), custom=$($status.mode_status.custom)"
    if ($status.premium_enabled) {
        Write-Host "[PASS] Premium is enabled" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Premium is disabled" -ForegroundColor Red
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 2. Create test signal
Write-Host "`n[2] POST /api/diag/premium-test" -ForegroundColor Yellow
try {
    $body = @{
        asset_id = 1
        symbol = "BTC-USDT"
        exchange = "OKX"
        premium_mode = "mr"
        side = "entry"
        action = "buy"
        reason_code = "MR_ENTRY_OSC"
        reason_text = "역추세 진입: OSC 하단밴드 신호 (R4)"
        tf = "1h"
    } | ConvertTo-Json

    $result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/diag/premium-test' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10
    Write-Host "ok: $($result.ok)"
    Write-Host "signal_id: $($result.signal_id)"
    Write-Host "snapshot_id: $($result.snapshot_id)"
    Write-Host "message: $($result.message)"
    if ($result.ok) {
        Write-Host "[PASS] Signal created successfully" -ForegroundColor Green
        $global:TestSignalId = $result.signal_id
        $global:TestSnapshotId = $result.snapshot_id
    } else {
        Write-Host "[FAIL] Signal creation failed" -ForegroundColor Red
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. List signals
Write-Host "`n[3] GET /api/premium/signals" -ForegroundColor Yellow
try {
    $signals = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/premium/signals?limit=5' -TimeoutSec 10
    Write-Host "ok: $($signals.ok)"
    Write-Host "total: $($signals.total)"
    if ($signals.signals.Count -gt 0) {
        Write-Host "Latest signal:"
        Write-Host "  signal_id: $($signals.signals[0].signal_id)"
        Write-Host "  symbol: $($signals.signals[0].symbol)"
        Write-Host "  side: $($signals.signals[0].side)"
        Write-Host "  reason_code: $($signals.signals[0].reason_code)"
        Write-Host "[PASS] Signals retrieved" -ForegroundColor Green
    } else {
        Write-Host "[WARN] No signals found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Get snapshot (if signal was created)
Write-Host "`n[4] GET /api/premium/snapshots/{id}" -ForegroundColor Yellow
if ($global:TestSnapshotId) {
    try {
        $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/premium/snapshots/$($global:TestSnapshotId)" -TimeoutSec 10
        Write-Host "ok: $($snapshot.ok)"
        if ($snapshot.ok) {
            Write-Host "snapshot_id: $($snapshot.snapshot.snapshot_id)"
            Write-Host "ohlcv: $($snapshot.snapshot.ohlcv | ConvertTo-Json -Compress)"
            Write-Host "indicators: $($snapshot.snapshot.indicators | ConvertTo-Json -Compress)"
            Write-Host "[PASS] Snapshot retrieved" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Snapshot not found" -ForegroundColor Red
        }
    } catch {
        Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "[SKIP] No snapshot ID available" -ForegroundColor Yellow
}

# 5. Test Premium OFF scenario
Write-Host "`n[5] Premium OFF Test (simulated check)" -ForegroundColor Yellow
Write-Host "To test Premium OFF: set PREMIUM_ENABLED=0 in .env and restart server"
Write-Host "[INFO] Current status shows premium_enabled=True" -ForegroundColor Cyan

Write-Host "`n=== Test Complete ===" -ForegroundColor Cyan
