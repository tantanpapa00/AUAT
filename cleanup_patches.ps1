$root = "C:\autobot"
$dst  = Join-Path $root ("_patch_archive\" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $dst | Out-Null

$patterns = @("patch_*.py","migrate_*.py","diag_*.py","okx_auth_check.py")
Get-ChildItem -Path $root -File -Include $patterns -ErrorAction SilentlyContinue | ForEach-Object {
  Move-Item -Force $_.FullName (Join-Path $dst $_.Name)
}

Write-Host "moved to $dst"
