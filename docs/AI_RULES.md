# AI_RULES — bbooster Hub (MUST FOLLOW)

## 0) Absolute Rules (NON-NEGOTIABLE)
1) SSOT 기준은 `docs/PROJECT_STATUS.md`만. (채팅/추정으로 완료 판정 금지)
2) 운영 루틴 고정: **stop → syntax → run → /tv test** (이 순서 외 금지)
3) Hub 원칙: **신호판단/추천/스크리닝/자동선정 X**
   - TradingView(또는 프리미엄전략 엔진)가 “신호”를 만든다.
   - Hub는 “브릿지 + 사이징/가드 + 안정성 + 기록/관측 + 실행”만 한다.
4) `/tv`는 **500 금지**. 예외는 반드시 `ok=false` + `code=exception` + `detail` 포함으로만 반환.
5) `/tv` 테스트는 **PowerShell** `Invoke-RestMethod` / `Invoke-WebRequest`만 사용 (curl JSON 이스케이프 금지)
6) **GitHub 레포 실물 기준(추정 금지)**:
   - 파일/경로/구조는 `git ls-files` 또는 리포 검색으로 “실제 존재” 확인 후 진행한다.
   - (예외) Release/Installer/패키징처럼 **배포본(zip)**을 다루는 작업에서만 zip 실물 확인을 수행한다.
   - 스코프 제외(절대 건드리지 않음): **SMC 전략/SMC 파일, MFT 캔들 관련 파일/로직**
7) “확인 안 하고 수정” 금지: 항상 **(코드검색/파일확인/엔드포인트 실측) → 문서 업데이트 → 작업 진행**

## 1) Work Start SOP (EVERY TASK)
매 작업 시작 시 반드시:
1) `docs/AI_RULES.md` 먼저 읽기
2) **touched files (planned)** 출력 → 작업 → **touched files (actual)** 출력

## 2) Evidence-Only Documentation (Token Saving)
- 긴 원문 증거(PS 출력/JSON/grep)는 **채팅에 붙이지 않는다**.
- 원문 증거는 `docs/APPENDIX_LOG.md`에만 **append-only**로 누적한다.
- 채팅에는 `docs/SSOT_HEADER.md`(20줄 이내)만 붙인다.
- 완료/미완료 판정은 반드시 **증거(파일/코드/엔드포인트 실측)**로만 한다.

## 3) Gates (DO NOT BREAK)
- Syntax gate: `python -m compileall app`
- Regression gate: `scripts/week4_regression.ps1 -FailOnContradiction`
- Gate 실패 시: **즉시 중단 → 원복/리버트 우선**(억지 진행 금지)

## 4) Safety & Security
- `.env` **값(키/시크릿)**은 절대 출력/문서화/로그에 남기지 않는다. (키 “목록”만 허용)
- E-STOP이 ON이면 실행/재시도(send-now 등) 경로는 **반드시 차단**되어야 한다.
- “설정값 ≠ 실제주문값”이면 주문을 **거부**(오주문 방지 정책 우선).
- 선물(Futures) 전면 미지원(설계/구현/QA 범위에서 제외).

## 5) Change Discipline (Small, Verifiable Steps)
- 한 번에 크게 바꾸지 말고, **작게 변경 → 즉시 실측 → 로그/문서 업데이트** 순서로 진행한다.
- hotfix가 누적된 `app/main.py`는 특히 **중복 def/오버라이드 위험**이 있으므로,
  - 호출 경로를 “증거로 고정(런타임 proof)”한 뒤 변경한다.
- 실패/모순이 보이면 “추측으로 메우지 말고” **증거를 먼저 확보**한다.
