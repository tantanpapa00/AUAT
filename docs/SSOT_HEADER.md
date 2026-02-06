# 큐브시스템 (QUBE System) — BBooster Hub
- Company: 큐브시스템 (QUBE System)
- Repo: C:\Users\pc\새 폴더\AUAT
- VPS: 76.13.180.30 (https://qube-system.com)
- SSOT: docs/FINISH_SSOT.md, docs/PROJECT_STATUS.md
- Rules: docs/AI_RULES.md (MUST read first)

## Current Status (2026-02-07)
- Week A~D: DONE (브랜드/사이트/PC앱/Android APK 기반)
- Day 6: DONE (대시보드 개편 + 구독 플랜)
- Day 7: DONE (종목분석 개편 + 10 버그 수정)
  - 신규 모듈: app/naver_finance.py, app/yahoo_finance.py
  - 자동완성/타임아웃/ETF/Admin 표시 수정

## Quick Commands
- Syntax: `python -m compileall app`
- Gates: `week4_regression.ps1`, `tv_template_regression.ps1`
- Server: `docker compose up -d` (VPS)
- PC App: `cd pc-app && cargo tauri dev`

## New APIs (Day 7)
- `/api/market/etf` — ETF 섹터별 분류
- `/api/market/crypto` — 암호화폐 시세
- `/api/analysis/rs` — 상대강도(RS) 분석
- `/api/analysis/new-high` — 52주 신고가
- `/api/analysis/valuation` — 밸류에이션 분석

## Scope Exclusions
- SMC strategy/files, MFT candle, Futures
