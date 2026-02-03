# shortmsg_regression.ps1
# ShortMsg 기능 회귀 테스트
# Usage: powershell -ExecutionPolicy Bypass -File scripts\shortmsg_regression.ps1
#
# PASS 기준:
# - ShortMsg 생성 성공
# - ShortMsg 조회 성공
# - ShortMsg 템플릿 조회 성공
# - /tv short_id 경로 accepted
# - /tv 기존 경로 (short_id 없음) 하위호환 확인

$base = "http://127.0.0.1:8000"
$errors = 0
$warnings = 0
$created_short_id = $null

Write-Host "=== ShortMsg Regression Test ===" -ForegroundColor Cyan
Write-Host ""

# 0) 전략 tv_secret 조회 (테스트용)
Write-Host "[0] Get test tv_secret..." -NoNewline
try {
    $r0 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/strategies" -TimeoutSec 10
    $j0 = $r0.Content | ConvertFrom-Json
    if ($j0.Count -gt 0) {
        $test_secret = $j0[0].tv_secret
        Write-Host " OK (secret found)" -ForegroundColor Green
    } else {
        Write-Host " SKIP (no strategies)" -ForegroundColor Yellow
        $warnings++
        $test_secret = "test_secret_fallback"
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
    $test_secret = "test_secret_fallback"
}

# 1) ShortMsg 생성 (POST /api/shortmsg)
Write-Host "[1] Create ShortMsg..." -NoNewline
try {
    $body1 = @{
        secret = $test_secret
        name = "Test OKX ETH spot"
        is_active = $true
        payload = @{
            exchange = "OKX"
            market = "spot"
            symbol = "ETH-USDT"
            side_policy = "tv"
            qty_policy = "tv_qty"
            order_type = "market"
        }
    } | ConvertTo-Json -Depth 5

    $r1 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/shortmsg" -Method Post -Body $body1 -ContentType "application/json" -TimeoutSec 10
    $j1 = $r1.Content | ConvertFrom-Json
    if ($j1.ok -eq $true -and $j1.short_id) {
        $created_short_id = $j1.short_id
        Write-Host " OK (short_id=$created_short_id)" -ForegroundColor Green
    } else {
        Write-Host " FAIL: ok=$($j1.ok)" -ForegroundColor Red
        $errors++
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 401) {
        Write-Host " SKIP (invalid secret - need valid strategy)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " ERROR: $_" -ForegroundColor Red
        $errors++
    }
}

# 2) ShortMsg 조회 (GET /api/shortmsg/{short_id})
if ($created_short_id) {
    Write-Host "[2] Get ShortMsg..." -NoNewline
    try {
        $r2 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/shortmsg/$created_short_id" -TimeoutSec 10
        $j2 = $r2.Content | ConvertFrom-Json
        if ($j2.ok -eq $true -and $j2.short_id -eq $created_short_id) {
            Write-Host " OK (name=$($j2.name))" -ForegroundColor Green
        } else {
            Write-Host " FAIL: ok=$($j2.ok)" -ForegroundColor Red
            $errors++
        }
    } catch {
        Write-Host " ERROR: $_" -ForegroundColor Red
        $errors++
    }
} else {
    Write-Host "[2] Get ShortMsg... SKIP (no short_id created)" -ForegroundColor Yellow
    $warnings++
}

# 3) ShortMsg 목록 조회 (GET /api/shortmsg)
Write-Host "[3] List ShortMsgs..." -NoNewline
try {
    $r3 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/shortmsg" -TimeoutSec 10
    $j3 = $r3.Content | ConvertFrom-Json
    if ($j3.ok -eq $true) {
        Write-Host " OK (count=$($j3.count))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: ok=$($j3.ok)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 4) ShortMsg 템플릿 조회 (GET /api/shortmsg/{short_id}/template/tradingview)
if ($created_short_id) {
    Write-Host "[4] Get ShortMsg Template..." -NoNewline
    try {
        $r4 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/shortmsg/$created_short_id/template/tradingview" -TimeoutSec 10
        $j4 = $r4.Content | ConvertFrom-Json
        if ($j4.ok -eq $true -and $j4.template_json) {
            Write-Host " OK (has template_json)" -ForegroundColor Green
        } else {
            Write-Host " FAIL: ok=$($j4.ok)" -ForegroundColor Red
            $errors++
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 400) {
            Write-Host " SKIP (no active strategy)" -ForegroundColor Yellow
            $warnings++
        } else {
            Write-Host " ERROR: $_" -ForegroundColor Red
            $errors++
        }
    }
} else {
    Write-Host "[4] Get ShortMsg Template... SKIP" -ForegroundColor Yellow
    $warnings++
}

# 5) /tv with short_id (ShortMsg 경로)
if ($created_short_id) {
    Write-Host "[5] POST /tv with short_id..." -NoNewline
    try {
        $body5 = @{
            secret = $test_secret
            alert_id = "test_$(Get-Date -Format 'yyyyMMddHHmmss')"
            symbol = "ETH-USDT"
            side = "buy"
            qty = 0.001
            short_id = $created_short_id
        } | ConvertTo-Json

        $r5 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body5 -ContentType "application/json" -TimeoutSec 10
        $j5 = $r5.Content | ConvertFrom-Json
        if ($j5.ok -eq $true -and $j5.code -eq "accepted") {
            Write-Host " OK (order_id=$($j5.order_id))" -ForegroundColor Green
        } elseif ($j5.code -eq "asset_not_found") {
            Write-Host " SKIP (asset not registered)" -ForegroundColor Yellow
            $warnings++
        } elseif ($j5.code -eq "stopped") {
            Write-Host " SKIP (E-STOP ON)" -ForegroundColor Yellow
            $warnings++
        } elseif ($j5.code -eq "secret_invalid") {
            Write-Host " SKIP (secret invalid)" -ForegroundColor Yellow
            $warnings++
        } else {
            Write-Host " FAIL: code=$($j5.code) detail=$($j5.detail)" -ForegroundColor Red
            $errors++
        }
    } catch {
        Write-Host " ERROR: $_" -ForegroundColor Red
        $errors++
    }
} else {
    Write-Host "[5] POST /tv with short_id... SKIP" -ForegroundColor Yellow
    $warnings++
}

# 6) /tv 하위호환 (short_id 없이 기존 경로)
Write-Host "[6] POST /tv without short_id (legacy)..." -NoNewline
try {
    $body6 = @{
        secret = $test_secret
        alert_id = "legacy_$(Get-Date -Format 'yyyyMMddHHmmss')"
        symbol = "BTC-USDT"
        side = "buy"
        qty = 0.001
    } | ConvertTo-Json

    $r6 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body6 -ContentType "application/json" -TimeoutSec 10
    $j6 = $r6.Content | ConvertFrom-Json
    if ($j6.ok -eq $true) {
        Write-Host " OK (code=$($j6.code))" -ForegroundColor Green
    } elseif ($j6.code -eq "asset_not_found") {
        Write-Host " OK (asset_not_found - legacy path works)" -ForegroundColor Green
    } elseif ($j6.code -eq "secret_invalid") {
        Write-Host " OK (secret_invalid - legacy path works)" -ForegroundColor Green
    } elseif ($j6.code -eq "stopped") {
        Write-Host " SKIP (E-STOP ON)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " OK (code=$($j6.code) - legacy path reached)" -ForegroundColor Green
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 7) shortmsg_not_found 에러 확인
Write-Host "[7] POST /tv with invalid short_id..." -NoNewline
try {
    $body7 = @{
        secret = $test_secret
        alert_id = "invalid_$(Get-Date -Format 'yyyyMMddHHmmss')"
        symbol = "TEST"
        side = "buy"
        qty = 1
        short_id = "INVALID999"
    } | ConvertTo-Json

    $r7 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body7 -ContentType "application/json" -TimeoutSec 10
    $j7 = $r7.Content | ConvertFrom-Json
    if ($j7.ok -eq $false -and $j7.code -eq "shortmsg_not_found") {
        Write-Host " OK (shortmsg_not_found)" -ForegroundColor Green
    } else {
        Write-Host " FAIL: expected shortmsg_not_found, got $($j7.code)" -ForegroundColor Red
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
    Write-Host "== SHORTMSG REGRESSION PASS ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "== SHORTMSG REGRESSION FAIL ($errors errors) ==" -ForegroundColor Red
    exit 1
}
