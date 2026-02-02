param(
  [string]$Pattern="main.py.week4_*.py",
  [string]$DownloadDir = "$env:USERPROFILE\Downloads",
  [string]$Target = "C:\autobot\app\main.py"
)

$src = Get-ChildItem $DownloadDir -File -Filter $Pattern |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $src) {
  Write-Host "NO PATCH FOUND in $DownloadDir pattern=$Pattern"
  exit 1
}

$bkdir = "C:\autobot\_archive\mainpy_backups"
New-Item -ItemType Directory -Force -Path $bkdir | Out-Null
$bk = Join-Path $bkdir ("main.py." + (Get-Date -Format "yyyyMMdd-HHmmss") + ".bak")

Copy-Item $Target $bk -Force
Copy-Item $src.FullName $Target -Force

Write-Host "APPLIED: $($src.FullName) -> $Target"
Write-Host "BACKUP : $bk"

# quick syntax check (fast)
python -m compileall C:\autobot\app | Select-Object -Last 10
