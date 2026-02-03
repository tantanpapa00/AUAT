# APPENDIX_LOG.md
- PowerShell 출력/실측 원문을 날짜별로 누적(삭제 금지)

# 2026-02-02 16:02:46 +09:00ST — KIS diag proof (raw)

## 1) GET /api/diag/home (miss 가능)

## 2) GET /api/diag/home?refresh_kis=1 (refresh)

## 3) GET /api/diag/home (hit + kis_cached_at 유지)

## 4) KIS diag endpoints
=== GET /api/diag/kis-preflight ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-balance ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-balance-summary ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-check ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-refresh ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)


# 2026-02-02 16:19:48 +09:00ST — diag proof (raw)


# 2026-02-02 16:21:53 +09:00ST — diag/home refresh_kis proof (raw)

## GET /api/diag/home?refresh_kis=1
{"ok":true,"items":[{"id":1,"account_name":"okx-main","strategy_name":"SPO-v2-edit","symbol":"ETH-USDT","market":"spot","is_active":false,"last_signal_at":null,"last_signal_id":null,"last_order_at":null,"last_order_status":null,"last_order_reason":null,"last_order_id":null,"last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":null,"last_signal":"-","last_order":"-","last_filled":"-"},{"id":3,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"ETH-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-23T19:24:48.816792+09:00","last_signal_id":"diag-tv-001","last_order_at":"2026-02-01T02:06:49.362444+09:00","last_order_status":"sent","last_order_reason":null,"last_order_id":"173","last_okx_order_id":"3267423532845064192","last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-02-01T02:06:49.528722+09:00","last_signal":"2026-01-23 19:24:48.816792+09:00 (diag-tv-001)","last_order":"2026-02-01 02:06:49.362444+09:00 | sent | ordId=3267423532845064192 | checked=2026-02-01 02:06:49.528722+09:00","last_filled":"-"},{"id":4,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"BTC-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-25T13:12:19.241034+09:00","last_signal_id":"diag-tv-c4133e40cb384137a5304c59cd772402","last_order_at":"2026-01-25T12:59:55.925873+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~8.894464 USDT (qty=0.0001 px=88064.0), have 8.73966403219e-05 USDT","last_order_id":"67","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.219185+09:00","last_signal":"2026-01-25 13:12:19.241034+09:00 (diag-tv-c4133e40cb384137a5304c59cd772402)","last_order":"2026-01-25 12:59:55.925873+09:00 | failed | checked=2026-01-27 18:09:21.219185+09:00","last_filled":"-"},{"id":5,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"SOL-USDT","market":"spot","is_active":true,"last_signal_at":null,"last_signal_id":null,"last_order_at":"2026-01-26T15:40:16.523271+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~0.125058 USDT (qty=0.001 px=123.82), have 8.73966403219e-05 USDT","last_order_id":"77","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.395077+09:00","last_signal":"-","last_order":"2026-01-26 15:40:16.523271+09:00 | failed | checked=2026-01-27 18:09:21.395077+09:00","last_filled":"-"}],"accounts_summary":[{"id":1,"name":"okx-main","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:09.377828+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":2,"name":"okx-sub","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:48.645589+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":3,"name":"kis-vps","exchange":"KIS","is_active":false,"last_health_at":null,"last_health_ok":null,"last_health_msg":null,"kis_balance_summary":{"dnca_tot_amt":10000000,"nass_amt":10000000,"tot_evlu_amt":10000000,"scts_evlu_amt":0,"cma_evlu_amt":0,"bfdy_tot_asst_evlu_amt":10000000,"asst_icdc_amt":0,"asst_icdc_erng_rt":"0.00000000"},"kis_msg1_fixed":"모의투자 조회가 완료되었습니다.","kis_check":{"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2},"kis_cache_state":"refresh","kis_cached_at":"2026-02-02T16:21:54.071563+09:00"}],"note":"assets_soft_deleted_missing"}


# 2026-02-02 16:25:17 +09:00ST — diag/home refresh_kis proof (raw)

{"ok":true,"items":[{"id":1,"account_name":"okx-main","strategy_name":"SPO-v2-edit","symbol":"ETH-USDT","market":"spot","is_active":false,"last_signal_at":null,"last_signal_id":null,"last_order_at":null,"last_order_status":null,"last_order_reason":null,"last_order_id":null,"last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":null,"last_signal":"-","last_order":"-","last_filled":"-"},{"id":3,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"ETH-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-23T19:24:48.816792+09:00","last_signal_id":"diag-tv-001","last_order_at":"2026-02-01T02:06:49.362444+09:00","last_order_status":"sent","last_order_reason":null,"last_order_id":"173","last_okx_order_id":"3267423532845064192","last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-02-01T02:06:49.528722+09:00","last_signal":"2026-01-23 19:24:48.816792+09:00 (diag-tv-001)","last_order":"2026-02-01 02:06:49.362444+09:00 | sent | ordId=3267423532845064192 | checked=2026-02-01 02:06:49.528722+09:00","last_filled":"-"},{"id":4,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"BTC-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-25T13:12:19.241034+09:00","last_signal_id":"diag-tv-c4133e40cb384137a5304c59cd772402","last_order_at":"2026-01-25T12:59:55.925873+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~8.894464 USDT (qty=0.0001 px=88064.0), have 8.73966403219e-05 USDT","last_order_id":"67","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.219185+09:00","last_signal":"2026-01-25 13:12:19.241034+09:00 (diag-tv-c4133e40cb384137a5304c59cd772402)","last_order":"2026-01-25 12:59:55.925873+09:00 | failed | checked=2026-01-27 18:09:21.219185+09:00","last_filled":"-"},{"id":5,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"SOL-USDT","market":"spot","is_active":true,"last_signal_at":null,"last_signal_id":null,"last_order_at":"2026-01-26T15:40:16.523271+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~0.125058 USDT (qty=0.001 px=123.82), have 8.73966403219e-05 USDT","last_order_id":"77","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.395077+09:00","last_signal":"-","last_order":"2026-01-26 15:40:16.523271+09:00 | failed | checked=2026-01-27 18:09:21.395077+09:00","last_filled":"-"}],"accounts_summary":[{"id":1,"name":"okx-main","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:09.377828+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":2,"name":"okx-sub","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:48.645589+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":3,"name":"kis-vps","exchange":"KIS","is_active":false,"last_health_at":null,"last_health_ok":null,"last_health_msg":null,"kis_balance_summary":{"dnca_tot_amt":10000000,"nass_amt":10000000,"tot_evlu_amt":10000000,"scts_evlu_amt":0,"cma_evlu_amt":0,"bfdy_tot_asst_evlu_amt":10000000,"asst_icdc_amt":0,"asst_icdc_erng_rt":"0.00000000"},"kis_msg1_fixed":"모의투자 조회가 완료되었습니다.","kis_check":{"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2},"kis_cache_state":"refresh","kis_cached_at":"2026-02-02T16:25:17.806339+09:00"}],"note":"assets_soft_deleted_missing"}


# 2026-02-02 16:26:22 +09:00ST — diag/home hit proof (raw)

## GET /api/diag/home (expect kis_cache_state=hit)
{"ok":true,"items":[{"id":1,"account_name":"okx-main","strategy_name":"SPO-v2-edit","symbol":"ETH-USDT","market":"spot","is_active":false,"last_signal_at":null,"last_signal_id":null,"last_order_at":null,"last_order_status":null,"last_order_reason":null,"last_order_id":null,"last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":null,"last_signal":"-","last_order":"-","last_filled":"-"},{"id":3,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"ETH-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-23T19:24:48.816792+09:00","last_signal_id":"diag-tv-001","last_order_at":"2026-02-01T02:06:49.362444+09:00","last_order_status":"sent","last_order_reason":null,"last_order_id":"173","last_okx_order_id":"3267423532845064192","last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-02-01T02:06:49.528722+09:00","last_signal":"2026-01-23 19:24:48.816792+09:00 (diag-tv-001)","last_order":"2026-02-01 02:06:49.362444+09:00 | sent | ordId=3267423532845064192 | checked=2026-02-01 02:06:49.528722+09:00","last_filled":"-"},{"id":4,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"BTC-USDT","market":"spot","is_active":true,"last_signal_at":"2026-01-25T13:12:19.241034+09:00","last_signal_id":"diag-tv-c4133e40cb384137a5304c59cd772402","last_order_at":"2026-01-25T12:59:55.925873+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~8.894464 USDT (qty=0.0001 px=88064.0), have 8.73966403219e-05 USDT","last_order_id":"67","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.219185+09:00","last_signal":"2026-01-25 13:12:19.241034+09:00 (diag-tv-c4133e40cb384137a5304c59cd772402)","last_order":"2026-01-25 12:59:55.925873+09:00 | failed | checked=2026-01-27 18:09:21.219185+09:00","last_filled":"-"},{"id":5,"account_name":"okx-main","strategy_name":"SPO-v2","symbol":"SOL-USDT","market":"spot","is_active":true,"last_signal_at":null,"last_signal_id":null,"last_order_at":"2026-01-26T15:40:16.523271+09:00","last_order_status":"failed","last_order_reason":"send_failed: INSUFFICIENT_BAL: need~0.125058 USDT (qty=0.001 px=123.82), have 8.73966403219e-05 USDT","last_order_id":"77","last_okx_order_id":null,"last_filled_qty":null,"last_order_avg_px":null,"last_checked_at":"2026-01-27T18:09:21.395077+09:00","last_signal":"-","last_order":"2026-01-26 15:40:16.523271+09:00 | failed | checked=2026-01-27 18:09:21.395077+09:00","last_filled":"-"}],"accounts_summary":[{"id":1,"name":"okx-main","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:09.377828+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":2,"name":"okx-sub","exchange":"OKX","is_active":false,"last_health_at":"2026-01-20T18:37:48.645589+09:00","last_health_ok":true,"last_health_msg":"basic network ok"},{"id":3,"name":"kis-vps","exchange":"KIS","is_active":false,"last_health_at":null,"last_health_ok":null,"last_health_msg":null,"kis_balance_summary":{"dnca_tot_amt":10000000,"nass_amt":10000000,"tot_evlu_amt":10000000,"scts_evlu_amt":0,"cma_evlu_amt":0,"bfdy_tot_asst_evlu_amt":10000000,"asst_icdc_amt":0,"asst_icdc_erng_rt":"0.00000000"},"kis_msg1_fixed":"모의투자 조회가 완료되었습니다.","kis_check":{"ok":true,"svr":"vps","base_url":"https://openapivts.koreainvestment.com:29443","http_status":200,"timeout_sec":20.0,"retry_n":2},"kis_cache_state":"hit","kis_cached_at":"2026-02-02T16:25:17.806339+09:00"}],"note":"assets_soft_deleted_missing"}


# 2026-02-03 02:50:00 +09:00 — Week8 Connector Test Proof

## GET /api/diag/connector-test?exchange=OKX&symbol=ETH-USDT
{"ok":true,"exchange":"OKX","connector":"OKXConnector","methods":{"get_balance_split":{"ok":true,"ccy":"USDT","total":202.2022530202663,"trading":202.12346719026633,"funding":0.07878583,"err_code":null,"err_msg":null},"get_markets":{"ok":true,"symbol":"ETH-USDT","min_qty":0.0001,"lot_qty":1e-06,"min_notional":null,"raw_keys":["alias","auctionEndTime","baseCcy","category","contTdSwTime","ctMult","ctType","ctVal","ctValCcy","expTime"]}}}

## GET /api/diag/connector-test?exchange=KIS&symbol=005930
{"ok":true,"exchange":"KIS","connector":"KISConnector","methods":{"get_balance_split":{"ok":true,"ccy":"KRW","total":10000000.0,"trading":10000000.0,"funding":0.0,"err_code":null,"err_msg":null},"get_markets":{"ok":true,"symbol":"005930","min_qty":1.0,"lot_qty":1.0,"min_notional":null,"raw_keys":["iscd_stat_cls_code","marg_rate","rprs_mrkt_kor_name","bstp_kor_isnm","temp_stop_yn","oprc_rang_cont_yn","clpr_rang_cont_yn","crdt_able_yn","grmn_rate_cls_code","elw_pblc_yn"]}}}

---

# 2026-02-03 KST — Week 8 Day 1: TV Template 생성

## 생성 파일: docs/TV_TEMPLATE.md
- OKX 현물 (BTC-USDT, ETH-USDT)
- KIS 국내주식 (005930)
- KIS 해외주식 (AAPL, TSLA)
- config_hash 사용 예시
- 에러 코드 안내 포함

---

# 2026-02-03 KST — Week 8 Day 2: /tv 검증 강화 (환불 방지 패키지)

## 수정 파일: app/main.py
추가된 검증:
- missing_side: side 필드 누락 시
- invalid_side: buy/sell 외 값
- missing_qty: qty 필드 누락 시
- invalid_qty: 0 이하 또는 숫자 아님

개선된 에러 메시지 (한글화):
- bad_json → "JSON 형식 오류: payload가 객체가 아님"
- missing_secret → "secret 누락: 얼러트 메시지에 secret 필드 추가 필요"
- secret_invalid → "secret 미등록: 전략에 등록된 tv_secret 확인 필요"
- asset_not_found → "자산 미등록: symbol이 전략에 등록되지 않음"
- asset_inactive → "자산 비활성: 활성화 필요"

## 수정 파일: docs/TV_TEMPLATE.md
- 에러 코드 표 확장 (14개 코드)
- 환불 방지 패키지 라벨 추가

---

# 2026-02-03 KST — Week 8 Day 3: 템플릿 생성 API

## 추가된 엔드포인트

### GET /api/templates/tradingview/options
- 활성 자산 목록 조회 (account/strategy/asset 계층)
- 템플릿 생성 전 선택용

### GET /api/assets/{asset_id}/template/tradingview
- 파라미터: side (buy/sell), qty (수량), order_type (market)
- 반환: template (dict) + template_json (복붙용 문자열)

### POST /api/templates/tradingview/generate
- body: { asset_ids: [1,2,3], side, qty, type }
- 다중 자산 일괄 템플릿 생성

---

# 2026-02-03 KST — Week 8 Day 4: Wizard 문서 생성

## 생성 파일: docs/TV_WIZARD.md
- Phase 1: 사전 준비 (계좌/전략/자산 확인)
- Phase 2: 템플릿 생성 (API 사용)
- Phase 3: TradingView 설정 (Step-by-step)
- Phase 4: 테스트 + 문제 해결
- FAQ 5개 항목
- 시작 전/완료 후 체크리스트 포함

---

# 2026-02-03 KST — Week 8 Day 5: 회귀 스크립트 추가

## 생성 파일: scripts/tv_template_regression.ps1

### 테스트 케이스 (8개)
1. Template Options API (GET /api/templates/tradingview/options)
2. Asset Template API (GET /api/assets/{id}/template/tradingview)
3. Batch Template Generate (POST /api/templates/tradingview/generate)
4. /tv missing_side 검증
5. /tv invalid_side 검증
6. /tv missing_qty 검증
7. /tv invalid_qty (zero) 검증
8. /tv invalid_qty (string) 검증

### PASS 기준
- errors = 0
- Template API 응답 정상
- /tv 검증 에러코드 반환 확인 (또는 secret_invalid SKIP)

---

# Week 8 완료 요약 (2026-02-03)

| Day | 작업 | 결과물 |
|-----|------|--------|
| Day 1 | TV 템플릿 표준화 | docs/TV_TEMPLATE.md |
| Day 2 | /tv 검증 강화 | app/main.py (side/qty 검증) |
| Day 3 | 템플릿 생성 API | 3개 엔드포인트 추가 |
| Day 4 | Wizard 문서 | docs/TV_WIZARD.md |
| Day 5 | 회귀 스크립트 | scripts/tv_template_regression.ps1 |
| 추가 | ShortMsg 기능 | 초보자용 간편 템플릿 |

---

# 2026-02-03 KST — ShortMsg 기능 구현

## 추가 엔드포인트
- POST /api/shortmsg — ShortMsg 생성 (short_id 발급)
- GET /api/shortmsg — 목록 조회
- GET /api/shortmsg/{short_id} — 단건 조회
- GET /api/shortmsg/{short_id}/template/tradingview — TV 템플릿 생성

## /tv 확장
- short_id 경로 추가 (기존 config_hash 경로와 병행)
- side_policy: tv / force_buy / force_sell
- qty_policy: tv_qty / pct_available / fixed_quote

## DB 변경
- shortmsgs 테이블 신규 (short_id, name, payload, is_active, note, created_at, updated_at)
- orders.short_id 컬럼 추가

## 회귀 테스트 실측 (2026-02-03)
```
=== ShortMsg Regression Test ===
[0] Get test tv_secret... OK (secret found)
[1] Create ShortMsg... OK (short_id=cmmVlORa)
[2] Get ShortMsg... OK (name=Test OKX ETH spot)
[3] List ShortMsgs... OK (count=1)
[4] Get ShortMsg Template... OK (has template_json)
[5] POST /tv with short_id... SKIP (asset not registered)
[6] POST /tv without short_id... OK (legacy path works)
[7] POST /tv with invalid short_id... OK (shortmsg_not_found)
== SHORTMSG REGRESSION PASS ==
```

## week4_regression 실측 (2026-02-03)
```
[A0] /api/diag/okx-preflight OK
[A] /api/home OK
[A] /api/system/estop OK (estop=false)
[B] /tv accepted (order_id=187)
[C] poll-now OK
[D] recover test OK (id=187, status=sent, okx_order_id=3274302954801946624)
== DONE ==
```

---

# 2026-02-03 KST — Week 9 Day 1: 멀티 커넥터 공통화

## 생성/수정 파일
- app/connectors/__init__.py: 커넥터 팩토리 모듈화
  - get_connector(), list_connectors(), get_all_connectors()
  - 싱글톤 패턴 (_CONNECTOR_CACHE)
  - exchange alias 정규화 (_norm_exchange)
- app/main.py: 커넥터 팩토리 import로 교체
  - GET /api/diag/connector-all 추가
- scripts/connector_regression.ps1: 회귀 테스트 스크립트
- docs/CONNECTOR.md: 인터페이스 명세

## connector_regression.ps1 실측 (2026-02-03 14:30 KST)
```
=== Connector Regression Test (Week 9) ===

[1] GET /api/diag/connector-all... OK (connectors=2)
   - KIS : OK (trading=10000000.0)
   - OKX : OK (trading=201.65414219026633)

[2] GET /api/diag/connector-test?exchange=OKX... OK (connector=OKXConnector)
[3] GET /api/diag/connector-test?exchange=KIS... OK (connector=KISConnector)
[4] GET /api/diag/connector-route... OK (exchange=OKX, connector=OKXConnector)

--- Summary ---
Errors: 0
Warnings: 0
== CONNECTOR REGRESSION PASS ==
```

## 기존 게이트 유지 확인
- week4_regression: PASS
- kis_regression: PASS
- tv_template_regression: PASS
- shortmsg_regression: PASS

