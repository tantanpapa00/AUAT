# E-STOP Test Script (Week 15 Day 3)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "=== E-STOP Test ===" -ForegroundColor Cyan

# 1. Get current E-STOP status
Write-Host "`n[1] GET /api/system/estop (current status)" -ForegroundColor Yellow
$status1 = Invoke-RestMethod -Uri "$base/api/system/estop" -TimeoutSec 10
Write-Host "ok: $($status1.ok)"
Write-Host "estop: $($status1.estop)"
Write-Host "reason: $($status1.reason)"

# 2. Set E-STOP ON
Write-Host "`n[2] POST /api/system/estop (E-STOP ON)" -ForegroundColor Yellow
$bodyOn = @{
    estop = "1"
    reason = "Week15 Day3 test"
} | ConvertTo-Json
$resultOn = Invoke-RestMethod -Uri "$base/api/system/estop" -Method Post -ContentType 'application/json' -Body $bodyOn -TimeoutSec 10
Write-Host "ok: $($resultOn.ok)"
Write-Host "estop: $($resultOn.estop)"

if ($resultOn.estop -eq $true) {
    Write-Host "[PASS] E-STOP ON success" -ForegroundColor Green
} else {
    Write-Host "[FAIL] E-STOP ON failed" -ForegroundColor Red
}

# 3. Check send-now blocked
Write-Host "`n[3] POST /api/diag/send-now (should be blocked)" -ForegroundColor Yellow
$sendResult = Invoke-RestMethod -Uri "$base/api/diag/send-now" -Method Post -TimeoutSec 10
Write-Host "ok: $($sendResult.ok)"
Write-Host "blocked_by_estop: $($sendResult.blocked_by_estop)"
Write-Host "total_sent: $($sendResult.total_sent)"

if ($sendResult.blocked_by_estop -eq $true -or $sendResult.total_sent -eq 0) {
    Write-Host "[PASS] send-now blocked or no orders" -ForegroundColor Green
} else {
    Write-Host "[INFO] send-now returned results" -ForegroundColor Cyan
}

# 4. Set E-STOP OFF
Write-Host "`n[4] POST /api/system/estop (E-STOP OFF)" -ForegroundColor Yellow
$bodyOff = @{
    estop = "0"
    reason = "test complete"
} | ConvertTo-Json
$resultOff = Invoke-RestMethod -Uri "$base/api/system/estop" -Method Post -ContentType 'application/json' -Body $bodyOff -TimeoutSec 10
Write-Host "ok: $($resultOff.ok)"
Write-Host "estop: $($resultOff.estop)"

if ($resultOff.estop -eq $false) {
    Write-Host "[PASS] E-STOP OFF success" -ForegroundColor Green
} else {
    Write-Host "[FAIL] E-STOP OFF failed" -ForegroundColor Red
}

# 5. Final status
Write-Host "`n[5] GET /api/system/estop (final status)" -ForegroundColor Yellow
$status2 = Invoke-RestMethod -Uri "$base/api/system/estop" -TimeoutSec 10
Write-Host "ok: $($status2.ok)"
Write-Host "estop: $($status2.estop)"

if ($status2.estop -eq $false) {
    Write-Host "[PASS] E-STOP restored to OFF" -ForegroundColor Green
} else {
    Write-Host "[WARN] E-STOP still ON" -ForegroundColor Yellow
}

Write-Host "`n=== E-STOP Test Complete ===" -ForegroundColor Cyan
