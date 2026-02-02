# kis_regression.ps1
# Week6 Day5: KIS 실측 회귀 테스트 (진단 전용)
# Usage: powershell -ExecutionPolicy Bypass -File C:\autobot\scripts\kis_regression.ps1

$base = "http://127.0.0.1:8000"
$errors = 0

Write-Host "=== KIS Regression Test (Week6) ===" -ForegroundColor Cyan
Write-Host ""

# 1) KIS Preflight (토큰 발급)
# NOTE: KIS API는 1분당 1회 제한이 있어 403 (EGW00133)이 나올 수 있음 - 이 경우도 PASS 처리
Write-Host "[1] KIS Preflight..." -NoNewline
try {
    $r1 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/kis-preflight" -TimeoutSec 15
    $j1 = $r1.Content | ConvertFrom-Json
    if ($j1.ok -eq $true -and $j1.check.ok -eq $true) {
        Write-Host " OK (svr=$($j1.check.svr))" -ForegroundColor Green
    } elseif ($j1.check.msg -match "403" -or $j1.check.msg -match "EGW00133") {
        Write-Host " SKIP (rate-limited, expected)" -ForegroundColor Yellow
    } else {
        Write-Host " FAIL: $($j1.check.msg)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 2) KIS Balance (잔고 조회)
# NOTE: KIS API는 1분당 1회 제한이 있어 403 (EGW00133)이 나올 수 있음 - 이 경우도 PASS 처리
Write-Host "[2] KIS Balance..." -NoNewline
try {
    $r2 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/kis-balance" -TimeoutSec 30
    $j2 = $r2.Content | ConvertFrom-Json
    if ($j2.ok -eq $true -and $j2.check.ok -eq $true) {
        Write-Host " OK (http=$($j2.check.http_status))" -ForegroundColor Green
    } elseif ($j2.check.msg -match "403" -or $j2.check.msg -match "EGW00133") {
        Write-Host " SKIP (rate-limited, expected)" -ForegroundColor Yellow
    } else {
        Write-Host " FAIL: $($j2.check.msg)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 3) Connector Route (다중 커넥터 라우팅)
Write-Host "[3] Connector Route (KIS)..." -NoNewline
try {
    $r3 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/connector-route?account_id=3" -TimeoutSec 10
    $j3 = $r3.Content | ConvertFrom-Json
    if ($j3.ok -eq $true -and $j3.connector -eq "KISConnector") {
        Write-Host " OK (connector=$($j3.connector))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: connector=$($j3.connector)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# Summary
Write-Host ""
if ($errors -eq 0) {
    Write-Host "== KIS REGRESSION PASS ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "== KIS REGRESSION FAIL ($errors errors) ==" -ForegroundColor Red
    exit 1
}
