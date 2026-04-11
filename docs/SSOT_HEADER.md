[SSOT_HEADER | bbooster Hub | COPY-PASTE]
- SSOT (repo): docs/PROJECT_STATUS.md @ <commit>
- Evidence (repo): docs/APPENDIX_LOG.md @ <commit>
- Rules: stop→syntax→run→/tv test | /tv 500 금지(ok=false+code=exception+detail)
- Scope: TV=신호, Hub=브릿지+가드+기록/관측+실행 | 추천/선정/스크리너/성과보장 X | Futures X
- Exclude: SMC/MFT 관련 파일/로직 절대 수정 금지
- Env: C:\autobot | http://127.0.0.1:8000 | /docs
- Gates: python -m compileall app | scripts/week4_regression.ps1 -FailOnContradiction (PASS 유지)
- Current: Week7 Day2 (KIS: diag 주문 테스트 + 심볼 정규화 규칙)
- Today Proof: PS 실측 원문은 APPENDIX_LOG에만 누적(채팅에 로그 붙이지 않음)
- NEXT 3:
  1) W7D2: KIS 주문 diag 엔드포인트(국내/해외 공통) + symbol_norm 확정
  2) W7D3: KIS polling(체결추적) + kis_state→internal status map 고정
  3) Gate 유지: 회귀 깨지면 즉시 원복
