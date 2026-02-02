from pathlib import Path
import re
from datetime import datetime

TARGET = Path(r"C:\autobot\app\main.py")

def backup(p: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(p.name + f".bak_okxfix_{ts}")
    bak.write_text(p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return bak

def ensure_import_os(src: str) -> str:
    if re.search(r"^\s*import\s+os\s*$", src, flags=re.M):
        return src

    # socket import 다음 줄에 넣는 걸 1순위로
    m = re.search(r"^(import\s+socket\s*)$", src, flags=re.M)
    if m:
        pos = m.end()
        return src[:pos] + "\nimport os\n" + src[pos:]

    # fallback: hashlib 다음
    m = re.search(r"^(import\s+hashlib\s*)$", src, flags=re.M)
    if m:
        pos = m.end()
        return src[:pos] + "\nimport os\n" + src[pos:]

    # fallback: 파일 최상단 import 블록 맨 위
    return "import os\n" + src

def ensure_dedup_key_in_orders_table(src: str) -> str:
    # 1) create table if not exists orders (...) 안에 dedup_key 컬럼 넣기
    # idem_source 바로 아래에 넣는 형태
    src = re.sub(
        r"(idem_source\s+text,\s*\n)",
        r"\1                dedup_key       text,\n",
        src,
        count=1
    )

    # 2) migration(기존 설치)에도 dedup_key 추가
    if 'add column if not exists dedup_key' not in src:
        src = re.sub(
            r'(db\.execute\(text\("alter table orders add column if not exists idem_source text;"\)\)\s*\n)',
            r'\1        db.execute(text("alter table orders add column if not exists dedup_key text;"))\n',
            src,
            count=1
        )
    return src

def make_tv_broker_fail_visible(src: str) -> str:
    # /tv 내부 broker send except Exception: pass 를
    # status=failed로 남기게 변경
    pattern = r"""
(\s*)except\s+Exception\s*:\s*\n
\1\s*pass\s*\n
"""
    repl = r"""\1except Exception as e:
\1    # broker 실패는 주문 row에 기록만 하고 /tv 응답은 accepted 유지
\1    try:
\1        _set_order_status(db, int(order_id), "failed", reason=str(e))
\1        db.commit()
\1    except Exception:
\1        try:
\1            db.rollback()
\1        except Exception:
\1            pass
"""
    return re.sub(pattern, repl, src, flags=re.X, count=1)

def main():
    if not TARGET.exists():
        raise SystemExit(f"ERR: not found: {TARGET}")

    bak = backup(TARGET)
    src = TARGET.read_text(encoding="utf-8", errors="replace")

    src2 = src
    src2 = ensure_import_os(src2)
    src2 = ensure_dedup_key_in_orders_table(src2)
    src2 = make_tv_broker_fail_visible(src2)

    if src2 == src:
        print("OK: nothing to patch (already looks fixed).")
        print("BACKUP:", bak)
        return

    TARGET.write_text(src2, encoding="utf-8")
    print("OK: patched main.py")
    print("BACKUP:", bak)

if __name__ == "__main__":
    main()
