param(
  [string]$Base = "http://127.0.0.1:8000",
  [string]$Secret = "dummy2",
  [string]$Symbol = "ETH-USDT",
  [string]$Side = "buy",
  [double]$Qty = 0.0001,
  [string]$Type = "market"
)

function J($obj, $depth=20) { $obj | ConvertTo-Json -Depth $depth }

Write-Host "== E-STOP Regression ==" -ForegroundColor Cyan
Write-Host "Base: $Base"

# 0) 상태 조회
Write-Host "`n[0] GET /api/system/estop"
try {
  $r = Invoke-RestMethod -Method Get -Uri "$Base/api/system/estop"
  J $r 10
} catch {
  Write-Host "FAILED: GET estop" -ForegroundColor Red
  throw
}

# 1) estop OFF
Write-Host "`n[1] POST /api/system/estop  (OFF)"
$body = @{ estop=$false; reason="regression off" } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$Base/api/system/estop" -ContentType "application/json" -Body $body
J $r 10

# 2) /tv 1회 (accepted 기대)
Write-Host "`n[2] POST /tv (expect accepted)"
$aid = "estop-reg-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$payload = @{ secret=$Secret; alert_id=$aid; symbol=$Symbol; side=$Side; qty=$Qty; type=$Type } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $payload
J $r 10

if (-not $r.ok) { throw "Expected ok=true on /tv when estop OFF" }

# 3) estop ON
Write-Host "`n[3] POST /api/system/estop  (ON)"
$body = @{ estop=$true; reason="regression on" } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$Base/api/system/estop" -ContentType "application/json" -Body $body
J $r 10

# 4) /tv 차단 (stopped 기대)
Write-Host "`n[4] POST /tv (expect stopped)"
$r = Invoke-RestMethod -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $payload
J $r 10
if ($r.ok -ne $false -or $r.code -ne "stopped") { throw "Expected ok=false, code=stopped on /tv when estop ON" }

# 5) send-now 차단
Write-Host "`n[5] POST /api/diag/send-now (expect stopped)"
$r = Invoke-RestMethod -Method Post -Uri "$Base/api/diag/send-now?limit=5"
J $r 10
if ($r.ok -ne $false -or $r.note -ne "stopped") { throw "Expected send-now stopped when estop ON" }

# 6) poll-now(poll) 차단
Write-Host "`n[6] POST /api/diag/poll-now?mode=poll (expect stopped)"
$r = Invoke-RestMethod -Method Post -Uri "$Base/api/diag/poll-now?mode=poll&limit=5"
J $r 10
if ($r.ok -ne $false -or $r.note -ne "stopped") { throw "Expected poll-now stopped when estop ON" }

# 7) recent 허용
Write-Host "`n[7] POST /api/diag/poll-now?mode=recent (expect ok=true)"
$r = Invoke-RestMethod -Method Post -Uri "$Base/api/diag/poll-now?mode=recent&limit=5"
J $r 10
if ($r.ok -ne $true) { throw "Expected recent ok=true when estop ON" }

Write-Host "`nPASS: E-STOP regression OK" -ForegroundColor Green
