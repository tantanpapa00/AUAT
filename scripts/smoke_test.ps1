# BBooster Smoke Test Script
# 10개 테스트 (정상 5개 + 실패 5개)

$passed = 0
$failed = 0

function Test-Smoke {
    param(
        [string]$name,
        [scriptblock]$scriptBlock,
        [bool]$expectOk
    )

    Write-Host "[$name] " -NoNewline
    try {
        $result = & $scriptBlock

        if ($null -eq $result) {
            if (-not $expectOk) {
                Write-Host "PASS (null expected)" -ForegroundColor Green
                $script:passed++
                return
            }
            Write-Host "FAIL (null result)" -ForegroundColor Red
            $script:failed++
            return
        }

        $ok = $result.ok

        if ($expectOk -and $ok) {
            Write-Host "PASS" -ForegroundColor Green
            $script:passed++
        } elseif (-not $expectOk -and -not $ok) {
            Write-Host "PASS (expected failure)" -ForegroundColor Green
            $script:passed++
        } else {
            Write-Host "FAIL (ok=$ok, expected=$expectOk)" -ForegroundColor Red
            $script:failed++
        }
    } catch {
        if (-not $expectOk) {
            Write-Host "PASS (exception expected)" -ForegroundColor Green
            $script:passed++
        } else {
            Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
            $script:failed++
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   BBooster Smoke Test (10 cases)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# === 정상 시나리오 (5개) ===
Write-Host "--- Normal Scenarios ---" -ForegroundColor Yellow

# SMOKE-01: Health Check
Test-Smoke "SMOKE-01: Health Check" {
    Invoke-RestMethod http://127.0.0.1:8000/api/diag/home -TimeoutSec 5
} $true

# SMOKE-02: /tv Webhook (secret 필드로 전략 인증)
Test-Smoke "SMOKE-02: /tv Webhook" {
    $body = @{
        secret = "dummy2"
        exchange = "OKX"
        symbol = "ETH-USDT"
        side = "buy"
        qty = "0.001"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10
} $true

# SMOKE-03: E-STOP Toggle (JSON body로 설정)
Test-Smoke "SMOKE-03: E-STOP Toggle" {
    # ON
    $onBody = @{ estop = $true } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $onBody -ContentType "application/json" -TimeoutSec 5
    $onResult = Invoke-RestMethod http://127.0.0.1:8000/api/system/estop -TimeoutSec 5
    $onState = $onResult.estop

    # OFF
    $offBody = @{ estop = $false } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $offBody -ContentType "application/json" -TimeoutSec 5
    $offResult = Invoke-RestMethod http://127.0.0.1:8000/api/system/estop -TimeoutSec 5
    $offState = $offResult.estop

    @{ ok = ($onState -eq $true -and $offState -eq $false) }
} $true

# SMOKE-04: Timeline
Test-Smoke "SMOKE-04: Timeline" {
    Invoke-RestMethod http://127.0.0.1:8000/api/timeline -TimeoutSec 5
} $true

# SMOKE-05: Connector
Test-Smoke "SMOKE-05: Connector" {
    Invoke-RestMethod "http://127.0.0.1:8000/api/diag/connector-test?exchange=OKX" -TimeoutSec 10
} $true

Write-Host ""
Write-Host "--- Failure Scenarios ---" -ForegroundColor Yellow

# === 실패 시나리오 (5개) ===

# SMOKE-06: Missing Secret (secret 필드 누락 테스트)
Test-Smoke "SMOKE-06: Missing Secret" {
    $body = @{
        exchange = "OKX"
        symbol = "ETH-USDT"
        side = "buy"
        qty = "0.001"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json" -TimeoutSec 5
} $false

# SMOKE-07: Invalid Secret (등록되지 않은 secret)
Test-Smoke "SMOKE-07: Invalid Secret" {
    $body = @{
        secret = "invalid_secret_12345"
        exchange = "OKX"
        symbol = "BTC-USDT"
        side = "buy"
        qty = "0.001"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json" -TimeoutSec 5
} $false

# SMOKE-08: Invalid Side (잘못된 side 값)
Test-Smoke "SMOKE-08: Invalid Side" {
    $body = @{
        secret = "dummy2"
        exchange = "OKX"
        symbol = "ETH-USDT"
        side = "invalid_side"
        qty = "0.001"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json" -TimeoutSec 5
} $false

# SMOKE-09: E-STOP Block (E-STOP ON 상태에서 주문 차단)
Test-Smoke "SMOKE-09: E-STOP Block" {
    # E-STOP ON
    $onBody = @{ estop = $true } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $onBody -ContentType "application/json" -TimeoutSec 5

    # Try send-now
    $body = @{ order_id = 99999 } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/diag/send-now -Method POST -Body $body -ContentType "application/json" -TimeoutSec 5

    # E-STOP OFF (restore)
    $offBody = @{ estop = $false } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $offBody -ContentType "application/json" -TimeoutSec 5

    # Check if blocked
    if ($result.ok -eq $false -or $result.note -match "estop" -or $result.count -eq 0) {
        @{ ok = $true }
    } else {
        @{ ok = $false }
    }
} $true

# SMOKE-10: 404 Endpoint
Test-Smoke "SMOKE-10: 404 Endpoint" {
    try {
        $null = Invoke-RestMethod http://127.0.0.1:8000/api/invalid/nonexistent/endpoint -TimeoutSec 5
        @{ ok = $false }  # Should not reach here
    } catch {
        @{ ok = $true }  # 404 exception expected
    }
} $true

# === Summary ===
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Results" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Passed: $passed / 10" -ForegroundColor $(if ($passed -eq 10) { "Green" } else { "Yellow" })
Write-Host "Failed: $failed / 10" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($failed -eq 0) {
    Write-Host "ALL SMOKE TESTS PASSED!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "SMOKE TEST FAILED!" -ForegroundColor Red
    exit 1
}
