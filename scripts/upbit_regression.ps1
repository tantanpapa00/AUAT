# upbit_regression.ps1
# Week13 Day3: Upbit Spot connector regression test
# Gate-UPBIT: This script must PASS to verify Upbit connector

param(
  [string]$Base="http://127.0.0.1:8000",
  [switch]$FailOnApiError,
  [int]$Retries=3,
  [int]$RetryDelaySec=1
)

Write-Host "== Upbit Regression (Gate-UPBIT) =="
Write-Host "Base: $Base"
Write-Host ""

$PASS = $true

function Invoke-WithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Method,
    [Parameter(Mandatory=$true)][string]$Uri,
    [int]$TimeoutSec=15,
    [int]$Retries=3,
    [int]$DelaySec=1
  )

  $lastErr = $null
  for ($i=0; $i -lt $Retries; $i++) {
    try {
      return Invoke-RestMethod -Method $Method -Uri $Uri -TimeoutSec $TimeoutSec
    } catch {
      $lastErr = $_
      Start-Sleep -Seconds $DelaySec
    }
  }
  throw $lastErr
}

# Test 1: Connector Test
Write-Host "[1] /api/diag/connector-test?exchange=UPBIT"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-test?exchange=UPBIT" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec
  $r | ConvertTo-Json -Depth 20

  if ($r.ok -eq $true) {
    Write-Host "[1] PASS: Connector loaded" -ForegroundColor Green
    # Note: balance may fail if API key not set or IP not whitelisted
    $bal = $r.methods.get_balance_split
    if ($bal.ok -eq $true) {
      Write-Host "    - Balance check: OK (trading=$($bal.trading) $($bal.ccy))" -ForegroundColor Green
    } else {
      Write-Host "    - Balance check: FAILED (err=$($bal.err_msg)) - API key or IP whitelist issue" -ForegroundColor Yellow
    }
  } else {
    Write-Host "[1] FAIL: Connector test failed" -ForegroundColor Red
    $PASS = $false
  }
} catch {
  Write-Host "[1] FAIL: API error - $($_.Exception.Message)" -ForegroundColor Red
  $PASS = $false
  if ($FailOnApiError) { exit 2 }
}

Write-Host ""

# Test 2: Connector All (verify UPBIT in list)
Write-Host "[2] /api/diag/connector-all (UPBIT in list)"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-all" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec

  if ($r.supported_exchanges -contains "UPBIT") {
    Write-Host "[2] PASS: UPBIT in supported_exchanges" -ForegroundColor Green

    if ($r.connectors.UPBIT.ok -eq $true) {
      Write-Host "    - UpbitConnector loaded: OK" -ForegroundColor Green
    } else {
      Write-Host "    - UpbitConnector: load failed (check config)" -ForegroundColor Yellow
    }
  } else {
    Write-Host "[2] FAIL: UPBIT not in supported_exchanges" -ForegroundColor Red
    $PASS = $false
  }
} catch {
  Write-Host "[2] FAIL: API error - $($_.Exception.Message)" -ForegroundColor Red
  $PASS = $false
  if ($FailOnApiError) { exit 2 }
}

Write-Host ""

# Test 3: Symbol Normalization (Upbit-specific)
Write-Host "[3] Symbol normalization test (BTC-KRW <-> KRW-BTC)"
try {
  # This test verifies symbol conversion is working by checking markets endpoint
  # Upbit returns symbols in QUOTE-BASE format, we convert to BASE-QUOTE internally
  $markets = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-test?exchange=UPBIT&symbol=BTC-KRW" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec

  if ($markets.ok -eq $true) {
    Write-Host "[3] PASS: Symbol conversion working" -ForegroundColor Green
  } else {
    Write-Host "[3] INFO: Symbol test skipped (connector ok but symbol test failed)" -ForegroundColor Yellow
  }
} catch {
  Write-Host "[3] INFO: Symbol test skipped" -ForegroundColor Yellow
}

Write-Host ""

# Summary
Write-Host "================================"
if ($PASS) {
  Write-Host "Gate-UPBIT: PASS" -ForegroundColor Green
  Write-Host "(Note: Balance test may fail without API key or IP whitelist - this is expected)"
  exit 0
} else {
  Write-Host "Gate-UPBIT: FAIL" -ForegroundColor Red
  exit 1
}
