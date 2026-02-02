$ErrorActionPreference = "Stop"
Set-Location "C:\autobot"

# 1) .env -> Env: 로드
$envPath = ".\.env"
if (-not (Test-Path $envPath)) { throw "Missing .env at $envPath" }

Write-Host "Loading .env into Env: ..."
$lines = Get-Content -Path $envPath -Encoding UTF8
foreach ($line in $lines) {
  $t = $line.Trim()
  if ($t.Length -eq 0 -or $t.StartsWith("#")) { continue }
  $pair = $t -split "=", 2
  if ($pair.Count -ne 2) { continue }
  $key = $pair[0].Trim()
  $val = $pair[1].Trim()
  if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
    $val = $val.Substring(1, $val.Length - 2)
  }
  if ($key.Length -eq 0) { continue }
  Set-Item -Path ("Env:\" + $key) -Value $val
}

# 2) 필수 키 검증 (없으면 즉시 중단)
$required = @(
  "DRY_RUN","ORDER_SUBMIT_ENABLE","ORDER_POLL_ENABLE",
  "OKX_SIMULATED","OKX_BASE_URL",
  "OKX_API_KEY","OKX_API_SECRET","OKX_API_PASSPHRASE"
)
$missing = @()
foreach ($k in $required) {
  $v = (Get-Item ("Env:\" + $k) -ErrorAction SilentlyContinue).Value
  if ($null -eq $v -or $v.Trim().Length -eq 0) { $missing += $k }
}
if ($missing.Count -gt 0) {
  Write-Host "Missing required env keys:" ($missing -join ", ")
  throw "Refusing to start server due to missing env"
}

# 3) 마스킹 출력
Write-Host "`n=== ENV CHECK (masked) ==="
Write-Host ("DRY_RUN={0}" -f $env:DRY_RUN)
Write-Host ("ORDER_SUBMIT_ENABLE={0}" -f $env:ORDER_SUBMIT_ENABLE)
Write-Host ("ORDER_POLL_ENABLE={0}" -f $env:ORDER_POLL_ENABLE)
Write-Host ("OKX_SIMULATED={0}" -f $env:OKX_SIMULATED)
Write-Host ("OKX_BASE_URL={0}" -f $env:OKX_BASE_URL)
$k = $env:OKX_API_KEY
if ($k.Length -gt 6) { $k = $k.Substring(0,3) + "***" + $k.Substring($k.Length-3,3) } else { $k = "***" }
Write-Host ("OKX_API_KEY={0}" -f $k)

# 4) uvicorn 실행 (이 창이 서버 콘솔)
Write-Host "`nStarting uvicorn..."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
