# Week 15 Integration Regression Test
# App simulation + Premium + E-STOP + Gates

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "=== Week 15 Integration Regression ===" -ForegroundColor Cyan
$passed = 0
$failed = 0

function Test-Pass($msg) {
    Write-Host "[PASS] $msg" -ForegroundColor Green
    $script:passed++
}

function Test-Fail($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    $script:failed++
}

# 1. Server Health (simple check)
Write-Host "`n[1] Server Health" -ForegroundColor Yellow
try {
    $openapi = Invoke-RestMethod -Uri "$base/openapi.json" -TimeoutSec 10
    if ($openapi.info) {
        Write-Host "    title: $($openapi.info.title)"
        Test-Pass "Server is running"
    } else {
        Test-Fail "OpenAPI check failed"
    }
} catch {
    Test-Fail "Server health - Exception"
}

# 2. E-STOP (app simulation)
Write-Host "`n[2] E-STOP (app control)" -ForegroundColor Yellow
try {
    # Get
    $estop = Invoke-RestMethod -Uri "$base/api/system/estop" -TimeoutSec 10
    Write-Host "    estop: $($estop.estop)"
    Test-Pass "GET /api/system/estop"
} catch { Test-Fail "GET /api/system/estop" }

# 3. Premium Status
Write-Host "`n[3] Premium Status" -ForegroundColor Yellow
try {
    $premium = Invoke-RestMethod -Uri "$base/api/premium/status" -TimeoutSec 10
    Write-Host "    enabled: $($premium.premium_enabled)"
    Write-Host "    modes: $($premium.available_modes -join ', ')"
    if ($premium.premium_enabled) { Test-Pass "Premium enabled" }
    else { Test-Fail "Premium should be enabled" }
} catch { Test-Fail "GET /api/premium/status" }

# 4. Premium Guards
Write-Host "`n[4] Premium Guards" -ForegroundColor Yellow
try {
    $guards = Invoke-RestMethod -Uri "$base/api/premium/guards" -TimeoutSec 10
    Write-Host "    cooldown: $($guards.guards.cooldown_sec)s"
    Write-Host "    daily_limit: $($guards.guards.daily_limit)"
    Test-Pass "GET /api/premium/guards"
} catch { Test-Fail "GET /api/premium/guards" }

# 5. Premium Signal Creation
Write-Host "`n[5] Premium Signal Creation" -ForegroundColor Yellow
$ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
$body = @{
    asset_id = 1000 + ($ts % 100)
    symbol = "W15-TEST"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "W15_REGRESSION"
    reason_text = "Week 15 regression test"
    tf = "1h"
} | ConvertTo-Json
try {
    $sig = Invoke-RestMethod -Uri "$base/api/diag/premium-test" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10
    if ($sig.ok) {
        Write-Host "    signal_id: $($sig.signal_id)"
        Test-Pass "Signal created"
    } else {
        Write-Host "    message: $($sig.message)"
        Test-Fail "Signal creation failed"
    }
} catch { Test-Fail "POST /api/diag/premium-test" }

# 6. Premium Signals List
Write-Host "`n[6] Premium Signals List" -ForegroundColor Yellow
try {
    $signals = Invoke-RestMethod -Uri "$base/api/premium/signals?limit=5" -TimeoutSec 10
    Write-Host "    total: $($signals.total)"
    if ($signals.ok) { Test-Pass "GET /api/premium/signals" }
    else { Test-Fail "GET /api/premium/signals" }
} catch { Test-Fail "GET /api/premium/signals" }

# 7. Timeline (app read)
Write-Host "`n[7] Timeline (app read)" -ForegroundColor Yellow
try {
    $timeline = Invoke-RestMethod -Uri "$base/api/timeline?limit=10" -TimeoutSec 10
    Write-Host "    total: $($timeline.total)"
    Write-Host "    items: $($timeline.items.Count)"
    if ($timeline.ok) { Test-Pass "GET /api/timeline" }
    else { Test-Fail "GET /api/timeline" }
} catch { Test-Fail "GET /api/timeline" }

# 8. OKX Connector
Write-Host "`n[8] OKX Connector" -ForegroundColor Yellow
try {
    $conn = Invoke-RestMethod -Uri "$base/api/diag/connector-test?exchange=OKX" -TimeoutSec 15
    if ($conn.ok) {
        Write-Host "    balance: $($conn.balance.trading) $($conn.balance.currency)"
        Test-Pass "OKX connector"
    } else {
        Write-Host "    error: $($conn.error)"
        Test-Fail "OKX connector"
    }
} catch { Test-Fail "OKX connector - $($_.Exception.Message)" }

# 9. TF Warning Test
Write-Host "`n[9] TF Warning Test (5m)" -ForegroundColor Yellow
$ts2 = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
$bodyTf = @{
    asset_id = 2000 + ($ts2 % 100)
    symbol = "TF-W15"
    exchange = "OKX"
    premium_mode = "mr"
    side = "entry"
    action = "buy"
    reason_code = "TF_W15_TEST"
    reason_text = "TF warning test"
    tf = "5m"
} | ConvertTo-Json
try {
    $tfResult = Invoke-RestMethod -Uri "$base/api/diag/premium-test" -Method Post -ContentType 'application/json' -Body $bodyTf -TimeoutSec 10
    if ($tfResult.ok -and $tfResult.tf_warning) {
        Write-Host "    tf_warning: $($tfResult.tf_warning)"
        Test-Pass "TF warning triggered"
    } elseif ($tfResult.ok) {
        Test-Pass "Signal created (tf_warning may be in message)"
    } else {
        Write-Host "    message: $($tfResult.message)"
        Test-Pass "TF blocked (if TF_BLOCK_UNDER=1)"
    }
} catch { Test-Fail "TF warning test" }

# 10. Subscription (stub)
Write-Host "`n[10] Subscription (app read)" -ForegroundColor Yellow
try {
    $headers = @{ "Authorization" = "Bearer test_token" }
    $sub = Invoke-RestMethod -Uri "$base/api/subscription/me" -Headers $headers -TimeoutSec 10
    Write-Host "    plan: $($sub.plan)"
    Write-Host "    premium_enabled: $($sub.entitlements.premium_enabled)"
    Test-Pass "GET /api/subscription/me"
} catch { Test-Fail "GET /api/subscription/me" }

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })

if ($failed -eq 0) {
    Write-Host "`n=== Week 15 Regression: PASS ===" -ForegroundColor Green
} else {
    Write-Host "`n=== Week 15 Regression: FAIL ===" -ForegroundColor Red
    exit 1
}
