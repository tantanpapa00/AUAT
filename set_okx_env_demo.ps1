# set_okx_env_demo.ps1
$env:DRY_RUN='0'
$env:OKX_BASE_URL='https://www.okx.com'
$env:OKX_SIMULATED='0'     # 데모면 1 / 라이브면 0
$env:OKX_TIMEOUT='10'

$env:OKX_API_KEY='582ed463-daad-4419-a3f4-5ba461966d38'
$env:OKX_API_SECRET='E1E8EF888F27CB85F015EA5A63BFC6BD'
$env:OKX_API_PASSPHRASE='Skarl0923!@'

$env:ORDER_POLL_ENABLE='1'
$env:ORDER_POLL_INTERVAL='5'
$env:ORDER_POLL_BATCH='20'

Write-Host "OKX env loaded. SIMULATED=$env:OKX_SIMULATED DRY_RUN=$env:DRY_RUN"
Write-Host ("KEY prefix=" + $env:OKX_API_KEY.Substring(0,[Math]::Min(6,$env:OKX_API_KEY.Length)) + "...")
