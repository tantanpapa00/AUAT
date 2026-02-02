# AI_RULES — bbooster Hub (MUST FOLLOW)

## 0) Absolute Rules (NON-NEGOTIABLE)
1) Do NOT modify anything related to SMC strategy/files or MFT candle files/logic.
2) Fixed routine only: stop → syntax → run → /tv test. Do not propose alternative sequences.
3) /tv must never return HTTP 500. Any exception must return: ok=false + code=exception + detail (with actionable message).
4) No assumptions. If not proven by file/grep/API output, mark as TODO and cite where to verify.
5) Always show touched files:
   - touched files (planned) BEFORE changes
   - touched files (actual) AFTER changes

## 1) SSOT & Evidence (Token-saving)
- Source of truth is repo docs (NOT chat):
  - docs/PROJECT_STATUS.md = SSOT-SLIM (keep short)
  - docs/APPENDIX_LOG.md   = raw PowerShell outputs (append-only, no summaries)
  - docs/SSOT_HEADER.md    = chat copy-paste header (<= 20 lines)
- Chat should only paste docs/SSOT_HEADER.md (and optionally commit hash). Never paste long logs in chat.

## 2) Gates (Quality)
- Syntax gate: python -m compileall app
- OKX regression gate: scripts/week4_regression.ps1 -FailOnContradiction
- KIS regression gate: scripts/kis_regression.ps1
- If gates fail: stop and revert (do not "push through").

## 3) Scope Policy (Product)
- TradingView makes signals. Hub only bridges + sizing/guards + stability + logs/observability + execution.
- No recommendations/selection/screener/auto-picking features.
- Futures are not supported (coin futures / domestic futures / overseas futures).

## 4) Security Principles
- Secret required for /tv (unless diag-only endpoints explicitly exempt).
- Keys must not be printed. Never include .env values in logs/docs.
- E-STOP must block execution paths immediately.

## 5) Evidence Logging Rule
- All PowerShell outputs used as proof must be appended to docs/APPENDIX_LOG.md with:
  - timestamp (KST)
  - command
  - raw output block
- Do not rewrite or summarize raw evidence inside APPENDIX_LOG.md.

## 6) Repo-based Workflow
- Working directory: C:\Users\pc\새 폴더\AUAT
- Work directly with repo files (git clone or local).
- Always verify file structure from repo before making changes.
- Before starting work: read docs/AI_RULES.md + docs/PROJECT_STATUS.md.
