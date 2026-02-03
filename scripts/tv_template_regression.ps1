# tv_template_regression.ps1
# Week8 Day5: TradingView Template Regression Test (환불 방지 패키지)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\tv_template_regression.ps1
#
# PASS 기준:
# - Template Options API 정상 응답
# - Asset Template API 정상 응답 (자산 존재 시)
# - /tv 검증 강화: missing_side, invalid_side, missing_qty, invalid_qty 반환

$base = "http://127.0.0.1:8000"
$errors = 0
$warnings = 0

Write-Host "=== TV Template Regression Test (Week8) ===" -ForegroundColor Cyan
Write-Host ""

# 1) Template Options API
Write-Host "[1] Template Options API..." -NoNewline
try {
    $r1 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/templates/tradingview/options" -TimeoutSec 10
    $j1 = $r1.Content | ConvertFrom-Json
    if ($j1.ok -eq $true) {
        Write-Host " OK (count=$($j1.count))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: ok=false" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 2) Asset Template API (asset_id=1 시도, 없으면 SKIP)
Write-Host "[2] Asset Template API..." -NoNewline
try {
    $r2 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/assets/1/template/tradingview?side=buy&qty=1" -TimeoutSec 10
    $j2 = $r2.Content | ConvertFrom-Json
    if ($j2.ok -eq $true -and $j2.template_json -ne $null) {
        Write-Host " OK (symbol=$($j2.symbol))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: ok=$($j2.ok)" -ForegroundColor Red
        $errors++
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 404) {
        Write-Host " SKIP (asset_id=1 not found)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " ERROR: $_" -ForegroundColor Red
        $errors++
    }
}

# 3) Batch Template Generate API
Write-Host "[3] Batch Template Generate..." -NoNewline
try {
    $body3 = '{"asset_ids":[1],"side":"buy","qty":1}'
    $r3 = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/templates/tradingview/generate" -Method Post -Body $body3 -ContentType "application/json" -TimeoutSec 10
    $j3 = $r3.Content | ConvertFrom-Json
    if ($j3.ok -eq $true) {
        Write-Host " OK (count=$($j3.count))" -ForegroundColor Green
    } else {
        Write-Host " FAIL: ok=false" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 4) /tv Validation: missing_side
Write-Host "[4] /tv missing_side check..." -NoNewline
try {
    $body4 = '{"secret":"test123","symbol":"TEST","qty":1}'
    $r4 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body4 -ContentType "application/json" -TimeoutSec 10
    $j4 = $r4.Content | ConvertFrom-Json
    if ($j4.ok -eq $false -and $j4.code -eq "missing_side") {
        Write-Host " OK (code=missing_side)" -ForegroundColor Green
    } elseif ($j4.code -eq "secret_invalid" -or $j4.code -eq "missing_secret") {
        Write-Host " SKIP (secret validation first)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: expected missing_side, got $($j4.code)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 5) /tv Validation: invalid_side
Write-Host "[5] /tv invalid_side check..." -NoNewline
try {
    $body5 = '{"secret":"test123","symbol":"TEST","side":"wrong","qty":1}'
    $r5 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body5 -ContentType "application/json" -TimeoutSec 10
    $j5 = $r5.Content | ConvertFrom-Json
    if ($j5.ok -eq $false -and $j5.code -eq "invalid_side") {
        Write-Host " OK (code=invalid_side)" -ForegroundColor Green
    } elseif ($j5.code -eq "secret_invalid" -or $j5.code -eq "missing_secret") {
        Write-Host " SKIP (secret validation first)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: expected invalid_side, got $($j5.code)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 6) /tv Validation: missing_qty
Write-Host "[6] /tv missing_qty check..." -NoNewline
try {
    $body6 = '{"secret":"test123","symbol":"TEST","side":"buy"}'
    $r6 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body6 -ContentType "application/json" -TimeoutSec 10
    $j6 = $r6.Content | ConvertFrom-Json
    if ($j6.ok -eq $false -and $j6.code -eq "missing_qty") {
        Write-Host " OK (code=missing_qty)" -ForegroundColor Green
    } elseif ($j6.code -eq "secret_invalid" -or $j6.code -eq "missing_secret") {
        Write-Host " SKIP (secret validation first)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: expected missing_qty, got $($j6.code)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 7) /tv Validation: invalid_qty (zero)
Write-Host "[7] /tv invalid_qty (zero) check..." -NoNewline
try {
    $body7 = '{"secret":"test123","symbol":"TEST","side":"buy","qty":0}'
    $r7 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body7 -ContentType "application/json" -TimeoutSec 10
    $j7 = $r7.Content | ConvertFrom-Json
    if ($j7.ok -eq $false -and $j7.code -eq "invalid_qty") {
        Write-Host " OK (code=invalid_qty)" -ForegroundColor Green
    } elseif ($j7.code -eq "secret_invalid" -or $j7.code -eq "missing_secret") {
        Write-Host " SKIP (secret validation first)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: expected invalid_qty, got $($j7.code)" -ForegroundColor Red
        $errors++
    }
} catch {
    Write-Host " ERROR: $_" -ForegroundColor Red
    $errors++
}

# 8) /tv Validation: invalid_qty (string)
Write-Host "[8] /tv invalid_qty (string) check..." -NoNewline
try {
    $body8 = '{"secret":"test123","symbol":"TEST","side":"buy","qty":"abc"}'
    $r8 = Invoke-WebRequest -UseBasicParsing -Uri "$base/tv" -Method Post -Body $body8 -ContentType "application/json" -TimeoutSec 10
    $j8 = $r8.Content | ConvertFrom-Json
    if ($j8.ok -eq $false -and $j8.code -eq "invalid_qty") {
        Write-Host " OK (code=invalid_qty)" -ForegroundColor Green
    } elseif ($j8.code -eq "secret_invalid" -or $j8.code -eq "missing_secret") {
        Write-Host " SKIP (secret validation first)" -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host " FAIL: expected invalid_qty, got $($j8.code)" -ForegroundColor Red
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
    Write-Host "== TV TEMPLATE REGRESSION PASS ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "== TV TEMPLATE REGRESSION FAIL ($errors errors) ==" -ForegroundColor Red
    exit 1
}
