$ErrorActionPreference = "SilentlyContinue"

# 1) uvicorn/app.main:app 프로세스 종료
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "uvicorn" -or $_.CommandLine -match "app\.main:app" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) 포트 8000 점유 프로세스 종료(남아있을 때 대비)
try {
  $conns = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
  foreach($c in $conns){
    if($c.OwningProcess){
      Stop-Process -Id $c.OwningProcess -Force
    }
  }
} catch {}

Write-Host "Stopped uvicorn/8000 processes (if any)."
