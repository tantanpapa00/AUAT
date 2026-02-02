param(
  [string]$Root="C:\autobot",
  [switch]$IncludeWeekPatches
)

$ts  = Get-Date -Format "yyyyMMdd-HHmmss"
$arc = Join-Path $Root "_archive\cleanup_$ts"

New-Item -ItemType Directory -Force -Path $arc | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $arc "app") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $arc "templates") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $arc "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $arc "patches") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $arc "logs") | Out-Null

# 1) app/ templates/ 백업·임시 파일 이동
Get-ChildItem (Join-Path $Root "app") -File -ErrorAction SilentlyContinue |
  ? { $_.Name -match '\.bak|\.old|\.tmp|~$' } |
  Move-Item -Destination (Join-Path $arc "app") -Force -ErrorAction SilentlyContinue

Get-ChildItem (Join-Path $Root "app\templates") -File -ErrorAction SilentlyContinue |
  ? { $_.Name -match '\.bak|\.old|\.tmp|~$' } |
  Move-Item -Destination (Join-Path $arc "templates") -Force -ErrorAction SilentlyContinue

# 2) data/ 비ASCII(깨진 파일명) 이동
Get-ChildItem (Join-Path $Root "data") -File -ErrorAction SilentlyContinue |
  ? { $_.Name -match '[^\u0000-\u007F]' } |
  Move-Item -Destination (Join-Path $arc "data") -Force -ErrorAction SilentlyContinue

# 3) 로그 이동
Get-ChildItem $Root -File -Filter "*.log" -ErrorAction SilentlyContinue |
  Move-Item -Destination (Join-Path $arc "logs") -Force -ErrorAction SilentlyContinue

# 4) (옵션) week patch 파일 모으기
if ($IncludeWeekPatches) {
  Get-ChildItem $Root -File -Filter "main.py.week4_*.py" -ErrorAction SilentlyContinue |
    Move-Item -Destination (Join-Path $arc "patches") -Force -ErrorAction SilentlyContinue
}

"== archived to =="
$arc
