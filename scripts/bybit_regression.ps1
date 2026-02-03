# bybit_regression.ps1
# Week12 Day5: Bybit Spot connector regression test
# Gate-BYBIT: This script must PASS to verify Bybit connector

param(
  [string]$Base="http://127.0.0.1:8000",
  [switch]$FailOnApiError,
  [int]$Retries=3,
  [int]$RetryDelaySec=1
)

Write-Host "== Bybit Regression (Gate-BYBIT) =="
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
Write-Host "[1] /api/diag/connector-test?exchange=BYBIT"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-test?exchange=BYBIT" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec
  $r | ConvertTo-Json -Depth 20

  if ($r.ok -eq $true) {
    Write-Host "[1] PASS: Connector loaded" -ForegroundColor Green
    # Note: balance may fail if no API key, but connector load is success
    $bal = $r.methods.get_balance_split
    if ($bal.ok -eq $true) {
      Write-Host "    - Balance check: OK (trading=$($bal.trading) $($bal.ccy))" -ForegroundColor Green
    } else {
      Write-Host "    - Balance check: FAILED (err=$($bal.err_msg)) - API key may not be set" -ForegroundColor Yellow
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

# Test 2: Connector All (verify BYBIT in list)
Write-Host "[2] /api/diag/connector-all (BYBIT in list)"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-all" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec

  if ($r.supported_exchanges -contains "BYBIT") {
    Write-Host "[2] PASS: BYBIT in supported_exchanges" -ForegroundColor Green

    if ($r.connectors.BYBIT.ok -eq $true) {
      Write-Host "    - BybitConnector loaded: OK" -ForegroundColor Green
    } else {
      Write-Host "    - BybitConnector: load failed (check config)" -ForegroundColor Yellow
    }
  } else {
    Write-Host "[2] FAIL: BYBIT not in supported_exchanges" -ForegroundColor Red
    $PASS = $false
  }
} catch {
  Write-Host "[2] FAIL: API error - $($_.Exception.Message)" -ForegroundColor Red
  $PASS = $false
  if ($FailOnApiError) { exit 2 }
}

Write-Host ""

# Summary
Write-Host "================================"
if ($PASS) {
  Write-Host "Gate-BYBIT: PASS" -ForegroundColor Green
  Write-Host "(Note: Balance test may fail without API key - this is expected)"
  exit 0
} else {
  Write-Host "Gate-BYBIT: FAIL" -ForegroundColor Red
  exit 1
}
