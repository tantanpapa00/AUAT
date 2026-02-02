param(
  [string]$Base="http://127.0.0.1:8000",
  [int]$Limit=20,
  [switch]$FailOnContradiction,
  [switch]$FailOnApiError,
  [int]$Retries=5,
  [int]$RetryDelaySec=1,
  [double]$Qty=0.0001
)

Write-Host "== Week4 Regression =="

function Invoke-WithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Method,
    [Parameter(Mandatory=$true)][string]$Uri,
    [string]$Body=$null,
    [string]$ContentType=$null,
    [int]$TimeoutSec=15,
    [int]$Retries=5,
    [int]$DelaySec=1
  )

  $lastErr = $null
  for ($i=0; $i -lt $Retries; $i++) {
    try {
      if ($null -ne $Body -and $Body.Length -gt 0) {
        if ($null -ne $ContentType -and $ContentType.Length -gt 0) {
          return Invoke-RestMethod -Method $Method -Uri $Uri -ContentType $ContentType -Body $Body -TimeoutSec $TimeoutSec
        } else {
          return Invoke-RestMethod -Method $Method -Uri $Uri -Body $Body -TimeoutSec $TimeoutSec
        }
      } else {
        return Invoke-RestMethod -Method $Method -Uri $Uri -TimeoutSec $TimeoutSec
      }
    } catch {
      $lastErr = $_
      Start-Sleep -Seconds $DelaySec
    }
  }
  throw $lastErr
}

function Try-Json {
  param(
    [Parameter(Mandatory=$true)][scriptblock]$Call,
    [string]$Label="call"
  )
  try {
    return & $Call
  } catch {
    Write-Warning ("{0} failed after retries: {1}" -f $Label, $_.Exception.Message)
    if ($FailOnApiError) { exit 2 }
    return $null
  }
}

# A0) OKX preflight (also verifies local server reachability)
Write-Host "`n[A0] /api/diag/okx-preflight"
Try-Json -Label "preflight" -Call {
  Invoke-WithRetry -Method Get -Uri "$Base/api/diag/okx-preflight" -TimeoutSec 10 -Retries $Retries -DelaySec $RetryDelaySec |
    ConvertTo-Json -Depth 30
} | Write-Output

# A) health-ish endpoints
Write-Host "`n[A] /api/home"
Try-Json -Label "/api/home" -Call {
  Invoke-WithRetry -Method Get -Uri "$Base/api/home" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec |
    ConvertTo-Json -Depth 50
} | Write-Output

Write-Host "`n[A] /api/system/estop"
Try-Json -Label "/api/system/estop" -Call {
  Invoke-WithRetry -Method Get -Uri "$Base/api/system/estop" -TimeoutSec 10 -Retries $Retries -DelaySec $RetryDelaySec |
    ConvertTo-Json -Depth 10
} | Write-Output

# B) /tv accepted
Write-Host "`n[B] /tv accepted"
$aid="wk4-reg-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$payload=@{ secret="dummy2"; alert_id=$aid; symbol="ETH-USDT"; side="buy"; qty=$Qty; type="market" } | ConvertTo-Json
$r = Invoke-WithRetry -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $payload -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec
$r | ConvertTo-Json -Depth 20
$orderId = $r.order_id
Write-Host "order_id=$orderId"

# C) poll-now
Write-Host "`n[C] poll-now"
Invoke-WithRetry -Method Post -Uri "$Base/api/diag/poll-now?mode=poll&limit=$Limit" -TimeoutSec 20 -Retries $Retries -DelaySec $RetryDelaySec |
  ConvertTo-Json -Depth 50

# D) recover test (requires db_prepare_recover.py v2)
Write-Host "`n[D] recover test (invalidate -> send-now -> symbol normalize)"
Push-Location C:\autobot

# Load DATABASE_URL only (do not print value)
if (-not $env:DATABASE_URL) {
  if (Test-Path .\.env) {
    $line = (Select-String -Path .\.env -Pattern '^\s*DATABASE_URL\s*=') | Select-Object -First 1
    if ($line) {
      $env:DATABASE_URL = (($line.Line -split '=',2)[1]).Trim().Trim('"').Trim("'")
    }
  }
}
Write-Host ("DATABASE_URL loaded: " + [bool]$env:DATABASE_URL)

python .\scripts\db_prepare_recover.py --order-id $orderId

Pop-Location

Invoke-WithRetry -Method Post -Uri "$Base/api/diag/send-now?limit=$Limit" -TimeoutSec 20 -Retries $Retries -DelaySec $RetryDelaySec |
  ConvertTo-Json -Depth 80

$od = Invoke-WithRetry -Method Get -Uri "$Base/api/diag/order?order_id=$orderId" -TimeoutSec 15 -Retries $Retries -DelaySec $RetryDelaySec
$od.item | Format-List id,symbol,status,submit_status,okx_order_id,okx_clord_id,okx_state,exch_status,filled_qty,avg_px,next_submit_at,submit_err

# E) contradiction check (filled evidence vs failed status)
$item = $od.item
$hasFilledEvidence = ($item.okx_state -eq "filled") -or ($item.exch_status -eq "filled") -or ($null -ne $item.filled_qty) -or ($null -ne $item.avg_px)
if (("$($item.status)" -match "failed") -and $hasFilledEvidence) {
  $msg = ("CONTRADICTION: status=" + $item.status + " but filled evidence exists (okx_state=" + $item.okx_state + ", exch_status=" + $item.exch_status + ", filled_qty=" + $item.filled_qty + ", avg_px=" + $item.avg_px + ")")
  Write-Warning $msg
  if ($FailOnContradiction) { exit 1 }
}

# W) hygiene warnings (do NOT fail; informational only)
Write-Host "`n[W] hygiene warnings (informational only)"
$mainPath = "C:\autobot\app\main.py"
if (Test-Path $mainPath) {
  $defs = Select-String -Path $mainPath -Pattern '^\s*def\s+okx_place_order\s*\('
  $cnt = if ($defs) { $defs.Count } else { 0 }
  Write-Host ("okx_place_order defs: " + $cnt)
  if ($defs) {
    foreach ($d in $defs) {
      Write-Host (" - line {0}: {1}" -f $d.LineNumber, ($d.Line.Trim()))
    }
  }

  $imports = Select-String -Path $mainPath -Pattern "app\.connectors|connectors\.okx|from\s+app\.connectors|import\s+okx_api|okx_api\." -AllMatches
  if (-not $imports) {
    Write-Warning "main.py has 0 references to connectors/okx or okx_api -> runtime may not use those modules (verify before refactor)"
  } else {
    Write-Host ("connector/okx_api references: " + $imports.Count)
  }
} else {
  Write-Warning ("main.py not found at: " + $mainPath)
}

Write-Host "`n== DONE =="