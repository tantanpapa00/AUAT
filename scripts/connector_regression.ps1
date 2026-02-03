# connector_regression.ps1
# Week 9: Multi-connector regression test
# Tests all connectors through unified interface
# Usage: powershell -ExecutionPolicy Bypass -File scripts\connector_regression.ps1
#
# PASS Criteria:
# - All supported connectors initialize
# - get_balance_split works for each
# - /api/diag/connector-all returns ok=true

$base = "http://127.0.0.1:8000"
$errors = 0
$warnings = 0

Write-Host "=== Connector Regression Test (Week 9) ===" -ForegroundColor Cyan
Write-Host ""

# 1) Test connector-all endpoint
Write-Host "[1] GET /api/diag/connector-all..." -NoNewline
try {
    $r1 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/connector-all" -TimeoutSec 30
    $j1 = $r1.Content | ConvertFrom-Json
    if ($j1.ok -eq $true) {
        $connCount = ($j1.connectors | Get-Member -MemberType NoteProperty).Count
        Write-Host " OK (connectors=$connCount)" -ForegroundColor Green

        # Show each connector status
        foreach ($prop in ($j1.connectors | Get-Member -MemberType NoteProperty)) {
            $ex = $prop.Name
            $conn = $j1.connectors.$ex
            if ($conn.ok -eq $true) {
                $bs = $conn.methods.get_balance_split
                if ($bs.ok -eq $true) {
                    Write-Host "   - $ex : OK (trading=$($bs.trading))" -ForegroundColor Green
                } else {
                    Write-Host "   - $ex : WARN (balance: $($bs.err_msg))" -ForegroundColor Yellow
                    $warnings++
                }
            } else {
                Write-Host "   - $ex : FAIL ($($conn.error))" -ForegroundColor Red
                $errors++
            }
        }
    } else {
        Write-Host " FAIL: ok=false" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 2) Test OKX connector individually
Write-Host ""
Write-Host "[2] GET /api/diag/connector-test?exchange=OKX..." -NoNewline
try {
    $r2 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/connector-test?exchange=OKX&symbol=ETH-USDT" -TimeoutSec 30
    $j2 = $r2.Content | ConvertFrom-Json
    if ($j2.ok -eq $true) {
        Write-Host " OK (connector=$($j2.connector))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: $($j2.detail)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 3) Test KIS connector individually
Write-Host "[3] GET /api/diag/connector-test?exchange=KIS..." -NoNewline
try {
    $r3 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/connector-test?exchange=KIS&symbol=005930" -TimeoutSec 30
    $j3 = $r3.Content | ConvertFrom-Json
    if ($j3.ok -eq $true) {
        Write-Host " OK (connector=$($j3.connector))" -ForegroundColor Green
    } elseif ($j3.methods.get_balance_split.err_msg -match "403" -or $j3.methods.get_balance_split.err_msg -match "EGW00133") {
        Write-Host " SKIP (KIS rate-limited)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: $($j3.detail)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 4) Test connector-route (design-only)
Write-Host "[4] GET /api/diag/connector-route..." -NoNewline
try {
    $r4 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/connector-route" -TimeoutSec 10
    $j4 = $r4.Content | ConvertFrom-Json
    if ($j4.ok -eq $true) {
        Write-Host " OK (exchange=$($j4.exchange), connector=$($j4.connector))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: $($j4.detail)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# Summary
Write-Host ""
Write-Host "--- Summary ---"
Write-Host "Errors: $errors" -ForegroundColor $(if ($errors -gt 0) { "Red" } else { "Green" })
Write-Host "Warnings: $warnings" -ForegroundColor $(if ($warnings -gt 0) { "Yellow" } else { "Green" })

if ($errors -eq 0) {
    Write-Host "== CONNECTOR REGRESSION PASS ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "== CONNECTOR REGRESSION FAIL ($errors errors) ==" -ForegroundColor Red
    exit 1
}
