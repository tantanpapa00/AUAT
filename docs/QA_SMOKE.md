# QA_SMOKE.md (스모크 테스트)
- Last updated: 2026-02-04 KST
- Status: Week B

> 스모크 테스트는 배포 전 필수 확인 항목입니다.
> 10개 테스트 (정상 5개 + 실패 5개) 모두 PASS 필수.

---

# 1) 테스트 환경

| 항목 | 요구사항 |
|------|----------|
| OS | Windows 10/11 64-bit |
| Python | 3.11+ |
| 서버 | http://127.0.0.1:8000 |
| 거래소 | OKX (테스트 계정) |

---

# 2) 정상 시나리오 (5개)

## SMOKE-01: 서버 시작 및 헬스체크
```powershell
# 실행
Invoke-RestMethod http://127.0.0.1:8000/api/diag/home

# 기대 결과
# ok: True
# estop: False (또는 True)
```
**PASS 조건**: `ok = True`

---

## SMOKE-02: /tv 웹훅 정상 수신
```powershell
$body = @{
    secret = "dummy2"  # 전략에 등록된 tv_secret
    exchange = "OKX"
    symbol = "ETH-USDT"
    side = "buy"
    qty = "0.001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"

# 기대 결과
# ok: True
# code: "accepted" 또는 "dry_run"
# order_id: (숫자)
```
**PASS 조건**: `ok = True` AND (`code = accepted` OR `code = dry_run`)

---

## SMOKE-03: E-STOP ON/OFF 토글
```powershell
# E-STOP ON (JSON body)
$onBody = @{ estop = $true } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $onBody -ContentType "application/json"
# 기대: ok=True, estop=True

# E-STOP OFF (JSON body)
$offBody = @{ estop = $false } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $offBody -ContentType "application/json"
# 기대: ok=True, estop=False
```
**PASS 조건**: ON 시 `estop = True`, OFF 시 `estop = False`

---

## SMOKE-04: 타임라인 조회
```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/timeline

# 기대 결과
# ok: True
# events: (배열)
```
**PASS 조건**: `ok = True` AND `events` 배열 존재

---

## SMOKE-05: 커넥터 상태 확인
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/diag/connector-test?exchange=OKX"

# 기대 결과
# ok: True
# exchange: "OKX"
# connector: "OKXConnector"
```
**PASS 조건**: `ok = True` AND `connector` 존재

---

# 3) 실패 시나리오 (5개)

## SMOKE-06: /tv 필수 필드 누락 (secret)
```powershell
$body = @{
    exchange = "OKX"
    symbol = "ETH-USDT"
    side = "buy"
    qty = "0.001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"

# 기대 결과
# ok: False
# code: "missing_secret"
```
**PASS 조건**: `ok = False`

---

## SMOKE-07: /tv 잘못된 secret
```powershell
$body = @{
    secret = "invalid_secret_12345"
    exchange = "OKX"
    symbol = "BTC-USDT"
    side = "buy"
    qty = "0.001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"

# 기대 결과
# ok: False
# code: "secret_invalid"
```
**PASS 조건**: `ok = False`

---

## SMOKE-08: /tv 잘못된 side
```powershell
$body = @{
    secret = "dummy2"
    exchange = "OKX"
    symbol = "ETH-USDT"
    side = "invalid_side"
    qty = "0.001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"

# 기대 결과
# ok: False
# code: "invalid_side"
```
**PASS 조건**: `ok = False`

---

## SMOKE-09: E-STOP ON 상태에서 주문 차단
```powershell
# 1. E-STOP ON (JSON body)
$onBody = @{ estop = $true } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $onBody -ContentType "application/json"

# 2. send-now 시도
$body = @{ order_id = 1 } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/diag/send-now -Method POST -Body $body -ContentType "application/json"

# 기대 결과
# ok: False 또는 차단 메시지 (note에 "estop" 포함)

# 3. E-STOP OFF (복원)
$offBody = @{ estop = $false } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop" -Method POST -Body $offBody -ContentType "application/json"
```
**PASS 조건**: E-STOP ON 상태에서 주문 차단됨

---

## SMOKE-10: 잘못된 엔드포인트 404
```powershell
try {
    Invoke-RestMethod http://127.0.0.1:8000/api/invalid/endpoint
} catch {
    $_.Exception.Response.StatusCode.value__
    # 기대: 404
}
```
**PASS 조건**: HTTP 404 반환

---

# 4) 스모크 테스트 스크립트

```powershell
# scripts/smoke_test.ps1
$passed = 0
$failed = 0
$results = @()

function Test-Smoke {
    param($name, $scriptBlock, $expectOk)

    Write-Host "[$name] " -NoNewline
    try {
        $result = & $scriptBlock
        $ok = $result.ok

        if ($expectOk -and $ok) {
            Write-Host "PASS" -ForegroundColor Green
            $script:passed++
            return @{ name = $name; status = "PASS" }
        } elseif (-not $expectOk -and -not $ok) {
            Write-Host "PASS (expected failure)" -ForegroundColor Green
            $script:passed++
            return @{ name = $name; status = "PASS" }
        } else {
            Write-Host "FAIL" -ForegroundColor Red
            $script:failed++
            return @{ name = $name; status = "FAIL"; result = $result }
        }
    } catch {
        if (-not $expectOk) {
            Write-Host "PASS (exception expected)" -ForegroundColor Green
            $script:passed++
            return @{ name = $name; status = "PASS" }
        }
        Write-Host "FAIL (exception)" -ForegroundColor Red
        $script:failed++
        return @{ name = $name; status = "FAIL"; error = $_.Exception.Message }
    }
}

Write-Host "=== BBooster Smoke Test ===" -ForegroundColor Cyan
Write-Host ""

# SMOKE-01
$results += Test-Smoke "SMOKE-01: Health Check" {
    Invoke-RestMethod http://127.0.0.1:8000/api/diag/home
} $true

# SMOKE-02
$results += Test-Smoke "SMOKE-02: /tv Webhook" {
    $body = @{ token="test"; exchange="OKX"; symbol="ETH-USDT"; side="buy"; qty="0.001" } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"
} $true

# SMOKE-03
$results += Test-Smoke "SMOKE-03: E-STOP Toggle" {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop?value=1" -Method POST
    $on = (Invoke-RestMethod http://127.0.0.1:8000/api/system/estop).estop
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop?value=0" -Method POST
    $off = (Invoke-RestMethod http://127.0.0.1:8000/api/system/estop).estop
    @{ ok = ($on -eq $true -and $off -eq $false) }
} $true

# SMOKE-04
$results += Test-Smoke "SMOKE-04: Timeline" {
    Invoke-RestMethod http://127.0.0.1:8000/api/timeline
} $true

# SMOKE-05
$results += Test-Smoke "SMOKE-05: Connector" {
    Invoke-RestMethod "http://127.0.0.1:8000/api/diag/connector-test?exchange=OKX"
} $true

# SMOKE-06 (expect failure)
$results += Test-Smoke "SMOKE-06: Missing Token" {
    $body = @{ exchange="OKX"; symbol="ETH-USDT"; side="buy"; qty="0.001" } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"
} $false

# SMOKE-07 (expect failure)
$results += Test-Smoke "SMOKE-07: Invalid Exchange" {
    $body = @{ token="test"; exchange="INVALID"; symbol="BTC-USDT"; side="buy"; qty="0.001" } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"
} $false

# SMOKE-08 (expect failure)
$results += Test-Smoke "SMOKE-08: Invalid Side" {
    $body = @{ token="test"; exchange="OKX"; symbol="BTC-USDT"; side="invalid"; qty="0.001" } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/tv -Method POST -Body $body -ContentType "application/json"
} $false

# SMOKE-09
$results += Test-Smoke "SMOKE-09: E-STOP Block" {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop?value=1" -Method POST
    $body = @{ order_id = 9999 } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/diag/send-now -Method POST -Body $body -ContentType "application/json"
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/estop?value=0" -Method POST
    @{ ok = ($result.ok -eq $false -or $result.note -match "estop") }
} $true

# SMOKE-10
$results += Test-Smoke "SMOKE-10: 404 Endpoint" {
    try {
        Invoke-RestMethod http://127.0.0.1:8000/api/invalid/endpoint
        @{ ok = $false }
    } catch {
        @{ ok = $true }
    }
} $true

Write-Host ""
Write-Host "=== Results ===" -ForegroundColor Cyan
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })

if ($failed -eq 0) {
    Write-Host "ALL SMOKE TESTS PASSED!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "SMOKE TEST FAILED!" -ForegroundColor Red
    exit 1
}
```

---

# 5) 실행 방법

```powershell
# 서버 실행 상태에서
cd C:\Users\pc\새 폴더\AUAT
.\scripts\smoke_test.ps1
```

---

# 6) 체크리스트 (배포 전)

- [ ] SMOKE-01 ~ SMOKE-10 전부 PASS
- [ ] Gate-OKX PASS
- [ ] Gate-TV PASS
- [ ] Gate-E-STOP PASS
- [ ] PC 설치 → 실행 → 대시보드 열림
- [ ] 진단 리포트 export 동작

---

[END OF QA_SMOKE]
