param(
  [string]$Base = "http://127.0.0.1:8000",
  [string]$Cfg  = "cfg_afac00e143ad",
  [string]$Symbol = "ETH-USDT"
)

Write-Host "Base=" $Base
Write-Host "Cfg =" $Cfg
Write-Host "Sym =" $Symbol

# 매 실행마다 고유 alert_id 생성
$runId = (Get-Date -Format "yyyyMMdd-HHmmss")
$aid   = "tv-w3d3-$runId"

# A) accepted 기대 (새 alert_id)
$body = @{ config_hash=$Cfg; alert_id=$aid; symbol=$Symbol; side="buy"; qty=0.0001; type="market" } | ConvertTo-Json -Compress
Write-Host "`n[A] accepted (new alert_id=$aid)"
Invoke-RestMethod -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 50

# B) ignored_duplicate 기대 (같은 alert_id 재전송)
Write-Host "`n[B] ignored_duplicate (same alert_id=$aid)"
Invoke-RestMethod -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 50

# C) unknown_config_hash 기대 (HTTP200 + ok:false)
$bodyBad = @{ config_hash="cfg_NOT_EXISTS"; alert_id="tv-w3d3-badcfg-$runId"; symbol=$Symbol; side="buy"; qty=0.0001; type="market" } | ConvertTo-Json -Compress
Write-Host "`n[C] unknown_config_hash (must NOT throw WebException)"
Invoke-RestMethod -Method Post -Uri "$Base/tv" -ContentType "application/json" -Body $bodyBad | ConvertTo-Json -Depth 50
