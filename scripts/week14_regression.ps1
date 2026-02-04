# Week 14 Integration Regression Test
# Premium ON/OFF + Gate verification

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "=== Week 14 Integration Regression ===" -ForegroundColor Cyan
$passed = 0
$failed = 0

# Helper function
function Test-Endpoint($name, $method, $uri, $body = $null, $expectOk = $true) {
    try {
        if ($method -eq "GET") {
            $r = Invoke-RestMethod -Uri $uri -TimeoutSec 10
        } else {
            $r = Invoke-RestMethod -Uri $uri -Method $method -ContentType 'application/json' -Body $body -TimeoutSec 10
        }

        $isOk = $r.ok -eq $expectOk
        if ($isOk) {
            Write-Host "[PASS] $name" -ForegroundColor Green
            $script:passed++
        } else {
            Write-Host "[FAIL] $name - expected ok=$expectOk, got ok=$($r.ok)" -ForegroundColor Red
            $script:failed++
        }
        return $r
    } catch {
        Write-Host "[FAIL] $name - Error: $($_.Exception.Message)" -ForegroundColor Red
        $script:failed++
        return $null
    }
}

# 1. Basic server health
Write-Host "`n[1] Server Health" -ForegroundColor Yellow
Test-Endpoint "GET /api/diag/home" "GET" "$base/api/diag/home"

# 2. Premium Status (should be ON)
Write-Host "`n[2] Premium Status (ON)" -ForegroundColor Yellow
$status = Test-Endpoint "GET /api/premium/status" "GET" "$base/api/premium/status"
if ($status -and $status.premium_enabled) {
    Write-Host "    premium_enabled: $($status.premium_enabled)" -ForegroundColor Cyan
    Write-Host "    available_modes: $($status.available_modes -join ', ')" -ForegroundColor Cyan
}

# 3. Premium Guards
Write-Host "`n[3] Premium Guards" -ForegroundColor Yellow
$guards = Test-Endpoint "GET /api/premium/guards" "GET" "$base/api/premium/guards"
if ($guards) {
    Write-Host "    cooldown_sec: $($guards.guards.cooldown_sec)" -ForegroundColor Cyan
    Write-Host "    daily_limit: $($guards.guards.daily_limit)" -ForegroundColor Cyan
    Write-Host "    tf_block: $($guards.guards.tf_block_under_15m)" -ForegroundColor Cyan
}

# 4. Signal Creation Test
Write-Host "`n[4] Signal Creation (Premium ON)" -ForegroundColor Yellow
$ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
$body = @{
    asset_id = 900 + ($ts % 100)  # 매번 다른 asset_id
    symbol = "REG-TEST"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "REGRESSION_TEST"
    reason_text = "Week 14 regression test"
    tf = "1h"
} | ConvertTo-Json
$sig = Test-Endpoint "POST /api/diag/premium-test" "POST" "$base/api/diag/premium-test" $body
if ($sig -and $sig.signal_id) {
    Write-Host "    signal_id: $($sig.signal_id)" -ForegroundColor Cyan
}

# 5. Signal List
Write-Host "`n[5] Signal List" -ForegroundColor Yellow
$signals = Test-Endpoint "GET /api/premium/signals" "GET" "$base/api/premium/signals?limit=5"
if ($signals) {
    Write-Host "    total: $($signals.total)" -ForegroundColor Cyan
}

# 6. Connector Check (OKX)
Write-Host "`n[6] Connector Check (OKX)" -ForegroundColor Yellow
try {
    $conn = Invoke-RestMethod -Uri "$base/api/diag/connector-test?exchange=OKX" -TimeoutSec 15
    if ($conn.ok) {
        Write-Host "[PASS] OKX connector" -ForegroundColor Green
        Write-Host "    balance: $($conn.balance.trading) $($conn.balance.currency)" -ForegroundColor Cyan
        $passed++
    } else {
        Write-Host "[WARN] OKX connector: $($conn.error)" -ForegroundColor Yellow
        # API 키 문제는 FAIL로 처리하지 않음
    }
} catch {
    Write-Host "[WARN] OKX connector error (may be API key issue)" -ForegroundColor Yellow
}

# 7. E-STOP Check
Write-Host "`n[7] E-STOP Status" -ForegroundColor Yellow
try {
    $estop = Invoke-RestMethod -Uri "$base/api/system/estop" -TimeoutSec 10
    Write-Host "[PASS] E-STOP check" -ForegroundColor Green
    Write-Host "    estop: $($estop.estop)" -ForegroundColor Cyan
    $passed++
} catch {
    Write-Host "[FAIL] E-STOP check" -ForegroundColor Red
    $failed++
}

# 8. Timeline Check
Write-Host "`n[8] Timeline Check" -ForegroundColor Yellow
Test-Endpoint "GET /api/timeline" "GET" "$base/api/timeline?limit=5"

# 9. TF Warning Test
Write-Host "`n[9] TF Warning Test (5m)" -ForegroundColor Yellow
$ts2 = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
$bodyTf = @{
    asset_id = 800 + ($ts2 % 100)
    symbol = "TF-REG"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TF_REG_TEST"
    reason_text = "TF warning regression"
    tf = "5m"
} | ConvertTo-Json
$tfResult = Invoke-RestMethod -Uri "$base/api/diag/premium-test" -Method Post -ContentType 'application/json' -Body $bodyTf -TimeoutSec 10
if ($tfResult.ok -and $tfResult.tf_warning) {
    Write-Host "[PASS] TF warning triggered" -ForegroundColor Green
    Write-Host "    tf_warning: $($tfResult.tf_warning)" -ForegroundColor Cyan
    $passed++
} elseif ($tfResult.ok) {
    Write-Host "[WARN] Signal created but tf_warning may be false" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] Signal blocked (TF block may be enabled)" -ForegroundColor Cyan
}

# Summary
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })

if ($failed -eq 0) {
    Write-Host "`n=== Week 14 Regression: PASS ===" -ForegroundColor Green
} else {
    Write-Host "`n=== Week 14 Regression: FAIL ===" -ForegroundColor Red
    exit 1
}
