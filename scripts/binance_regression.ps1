# binance_regression.ps1
# Week12 Day5: Binance Spot connector regression test
# Gate-BINANCE: This script must PASS to verify Binance connector

param(
  [string]$Base="http://127.0.0.1:8000",
  [switch]$FailOnApiError,
  [int]$Retries=3,
  [int]$RetryDelaySec=1
)

Write-Host "== Binance Regression (Gate-BINANCE) =="
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
Write-Host "[1] /api/diag/connector-test?exchange=BINANCE"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-test?exchange=BINANCE" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec
  $r | ConvertTo-Json -Depth 20

  if ($r.ok -eq $true) {
    Write-Host "[1] PASS: Connector loaded, balance check ok=$($r.methods.get_balance_split.ok)" -ForegroundColor Green
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

# Test 2: Connector All (verify BINANCE in list)
Write-Host "[2] /api/diag/connector-all (BINANCE in list)"
try {
  $r = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/connector-all" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec

  if ($r.supported_exchanges -contains "BINANCE") {
    Write-Host "[2] PASS: BINANCE in supported_exchanges" -ForegroundColor Green

    if ($r.connectors.BINANCE.ok -eq $true) {
      Write-Host "    - BinanceConnector loaded: OK" -ForegroundColor Green
      $bal = $r.connectors.BINANCE.methods.get_balance_split
      if ($null -ne $bal) {
        Write-Host "    - Balance ($($bal.ccy)): total=$($bal.total), trading=$($bal.trading)"
      }
    } else {
      Write-Host "    - BinanceConnector: FAILED (check API keys)" -ForegroundColor Yellow
    }
  } else {
    Write-Host "[2] FAIL: BINANCE not in supported_exchanges" -ForegroundColor Red
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
  Write-Host "Gate-BINANCE: PASS" -ForegroundColor Green
  exit 0
} else {
  Write-Host "Gate-BINANCE: FAIL" -ForegroundColor Red
  exit 1
}
