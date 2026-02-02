# kis_regression.ps1
# Week7 Day5: KIS MVP 회귀 테스트 (place_order/get_order/polling/routing)
# Usage: powershell -ExecutionPolicy Bypass -File C:\autobot\scripts\kis_regression.ps1

$base = "http://127.0.0.1:8000"
$errors = 0
$warnings = 0

Write-Host "=== KIS MVP Regression Test (Week7) ===" -ForegroundColor Cyan
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

# 4) KIS Order Test (DRY_RUN 모드 - 토큰/해시키 검증)
# NOTE: DRY_RUN=1이 아니면 dry_run_required 반환 (정상 동작)
Write-Host "[4] KIS Order Test (DRY_RUN)..." -NoNewline
try {
    $r4 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/kis-order-test?symbol=005930&side=buy&qty=1" -TimeoutSec 20
    $j4 = $r4.Content | ConvertFrom-Json
    if ($j4.ok -eq $true -and $j4.dry_run -eq $true) {
        Write-Host " OK (connector=$($j4.connector), token_valid=$($j4.token_valid), hashkey_ok=$($j4.hashkey_ok))" -ForegroundColor Green
    } elseif ($j4.code -eq "dry_run_required") {
        Write-Host " SKIP (DRY_RUN=1 not set, expected in prod)" -ForegroundColor Yellow
        $warnings++
    } elseif ($j4.code -eq "token_fail") {
        Write-Host " SKIP (token fail, check KIS creds)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: code=$($j4.code) detail=$($j4.detail)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 5) KIS Poll Test (체결 추적 폴링)
# NOTE: 폴링 대상 주문이 없어도 ok=true 반환 (polled=[])
Write-Host "[5] KIS Poll Test..." -NoNewline
try {
    $r5 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/kis-poll-test?limit=5" -TimeoutSec 30
    $j5 = $r5.Content | ConvertFrom-Json
    if ($j5.ok -eq $true) {
        $polledCount = 0
        if ($j5.polled -ne $null) { $polledCount = $j5.polled.Count }
        Write-Host " OK (polled=$polledCount)" -ForegroundColor Green
    } else {
        Write-Host " FAIL: code=$($j5.code) detail=$($j5.detail)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 6) Send-Now KIS Routing 검증 (실제 전송 없이 라우팅만 확인)
# NOTE: E-STOP ON이면 stopped 반환, 대상 주문 없으면 ok=true + items=[]
Write-Host "[6] Send-Now (KIS routing check)..." -NoNewline
try {
    $r6 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/diag/send-now?limit=1" -Method Post -TimeoutSec 20
    $j6 = $r6.Content | ConvertFrom-Json
    if ($j6.ok -eq $true) {
        Write-Host " OK (note=$($j6.note))" -ForegroundColor Green
    } elseif ($j6.note -eq "stopped") {
        Write-Host " SKIP (E-STOP ON, expected)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: ok=$($j6.ok) note=$($j6.note)" -ForegroundColor Red
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
    Write-Host "== KIS MVP REGRESSION PASS ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "== KIS MVP REGRESSION FAIL ($errors errors) ==" -ForegroundColor Red
    exit 1
}
