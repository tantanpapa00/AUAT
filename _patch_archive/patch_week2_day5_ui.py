import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\autobot")
INDEX = ROOT / "app" / "templates" / "index.html"
MAIN  = ROOT / "app" / "main.py"

def backup(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    b = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, b)
    return b

def clean_index_html(text: str) -> str:
    lines = text.splitlines()

    # (1) 맨 앞에 PowerShell here-string "@'" 라인이 있으면 제거
    if lines and lines[0].strip() == "@'":
        lines = lines[1:]

    # (2) 맨 뒤에 "'@ | Set-Content ..." 같은 PowerShell 꼬리가 있으면 제거
    #     - 보통 마지막 줄이 "'@ | Set-Content ..." 또는 "'@" 로 시작
    while lines and lines[-1].strip().startswith("'@"):
        lines = lines[:-1]

    # (3) 파일 중간에 "Set-Content ..." 같은 PowerShell 라인이 섞여있으면 제거(안전)
    cleaned = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("Set-Content ") or s.startswith("| Set-Content ") or s.startswith("Out-File "):
            continue
        cleaned.append(ln)

    return "\n".join(cleaned).rstrip() + "\n"

def ensure_health_route(text: str) -> str:
    if '@app.get("/health")' in text:
        return text

    insert = """

@app.get("/health")
def health():
    # Simple liveness probe for UI/browser.
    return {"ok": True}
"""

    # main.py는 /db-check 라우트가 있으니 그 뒤에 넣는 방식(앵커 실패 방지: 좀 더 유연)
    marker = '@app.get("/db-check")'
    pos = text.find(marker)
    if pos == -1:
        # 못 찾으면 그냥 파일 맨 위(app 생성 이후) 근처에 넣기
        app_marker = "app = FastAPI("
        pos2 = text.find(app_marker)
        if pos2 == -1:
            return text + insert
        # app 선언 뒤에 삽입
        endline = text.find("\n", pos2)
        return text[:endline+1] + insert + text[endline+1:]

    # /db-check 함수 블록 끝 다음에 삽입(간단히 다음 "# ---- Accounts API ----" 앞에 삽입 시도)
    anchor2 = "# ---- Accounts API ----"
    posA = text.find(anchor2, pos)
    if posA != -1:
        return text[:posA] + insert + "\n" + text[posA:]

    # 그래도 못 찾으면 /db-check marker 뒤쪽에 그냥 붙임
    return text + insert

def main():
    if not INDEX.exists():
        raise SystemExit(f"index.html not found: {INDEX}")
    if not MAIN.exists():
        raise SystemExit(f"main.py not found: {MAIN}")

    b1 = backup(INDEX)
    b2 = backup(MAIN)
    print("Backup created:")
    print(" -", b1)
    print(" -", b2)

    idx = INDEX.read_text(encoding="utf-8", errors="replace")
    idx2 = clean_index_html(idx)
    INDEX.write_text(idx2, encoding="utf-8")
    print("Cleaned:", INDEX)

    mp = MAIN.read_text(encoding="utf-8", errors="replace")
    mp2 = ensure_health_route(mp)
    MAIN.write_text(mp2, encoding="utf-8")
    print("Ensured /health:", MAIN)

if __name__ == "__main__":
    main()
