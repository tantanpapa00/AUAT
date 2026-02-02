# -*- coding: utf-8 -*-
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\autobot")
TARGET = ROOT / "app" / "main.py"

def backup_file(p: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(p.name + f".bak_okxbroker_{ts}")
    bak.write_text(p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return bak

def ensure_import(src: str, line: str, after_pat: str) -> str:
    if re.search(rf"^{re.escape(line)}\s*$", src, flags=re.M):
        return src
    m = re.search(after_pat, src, flags=re.M)
    if not m:
        m = re.search(r"^(import|from)\s+.+$", src, flags=re.M)
    if not m:
        return line + "\n" + src
    pos = m.end()
    return src[:pos] + "\n" + line + src[pos:]

def indent_block(block: str, spaces: int) -> str:
    pref = " " * spaces
    out = []
    for ln in block.splitlines():
        out.append((pref + ln) if ln.strip() else ln)
    return "\n".join(out)

def main():
    if not TARGET.exists():
        raise SystemExit(f"ERR: not found: {TARGET}")

    bak = backup_file(TARGET)
    src = TARGET.read_text(encoding="utf-8", errors="replace")

    # Already patched?
    if "def _maybe_send_to_broker(" in src and "def okx_place_order(" in src:
        print("OK: already patched.")
        print("BACKUP:", bak)
        return

    # Ensure imports (main.py 쪽에 필요한 것들)
    src = ensure_import(src, "import os", r"^import hashlib\s*$")
    src = ensure_import(src, "import base64", r"^import os\s*$")
    src = ensure_import(src, "import hmac", r"^import base64\s*$")

    # Insert helpers after _mk_idem_key
    mk_pat = r"def _mk_idem_key\([^\n]*\):\n(?:[ \t].*\n)+"
    m = re.search(mk_pat, src)
    if not m:
        raise SystemExit("ERR: cannot find def _mk_idem_key(...)")

    # ✅ v2: 바깥 helpers를 ''' 로 감싸서 내부 text(\"\"\"...\"\"\") 충돌 제거
    helpers = r'''
def _is_dry_run() -> bool:
    v = os.getenv("DRY_RUN", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return "null"


def _set_order_status(db: Session, order_id: int, status: str, *, okx_order_id=None, okx_response=None, reason=None):
    params = {"id": int(order_id), "status": str(status)}
    if okx_order_id is not None:
        params["okx_order_id"] = str(okx_order_id)
    if okx_response is not None:
        params["okx_response"] = _safe_json(okx_response)
    if reason is not None:
        params["reason"] = str(reason)

    db.execute(
        text(
            """
            update orders
            set
                status = :status,
                updated_at = now(),
                okx_order_id = coalesce(:okx_order_id, okx_order_id),
                okx_response = coalesce(cast(:okx_response as jsonb), okx_response),
                reason = coalesce(:reason, reason)
            where id = :id
            """
        ),
        {
            "id": params.get("id"),
            "status": params.get("status"),
            "okx_order_id": params.get("okx_order_id"),
            "okx_response": params.get("okx_response"),
            "reason": params.get("reason"),
        },
    )


def _maybe_send_to_broker(db: Session, *, order_id: int, symbol: str, side: str, qty: float, order_type: str | None):
    # dry-run이면 상태 전이도 하지 않음 (원하면 여기서 sending/sent 시뮬레이션으로 바꿔도 됨)
    if _is_dry_run():
        return

    _set_order_status(db, int(order_id), "sending")
    db.commit()

    try:
        okx_result = None
        try:
            okx_result = okx_place_order(symbol=symbol, side=side, qty=qty, type=order_type or "market")
        except NameError:
            raise RuntimeError("okx_place_order not wired yet")

        okx_order_id = None
        if isinstance(okx_result, dict):
            okx_order_id = okx_result.get("ordId") or okx_result.get("okx_order_id")

        _set_order_status(db, int(order_id), "sent", okx_order_id=okx_order_id, okx_response=okx_result)
        db.commit()
    except Exception as e:
        _set_order_status(db, int(order_id), "failed", reason=str(e))
        db.commit()
'''

    src = src[:m.end()] + helpers + src[m.end():]

    # Inject broker call before "if not created:"
    if_pat = r"\n(\s+if not created:)"
    mm = re.search(if_pat, src)
    if not mm:
        raise SystemExit("ERR: cannot find insertion point: 'if not created:'")

    broker_call = """
# 4.5) optional broker send (guarded)
if created and order_id is not None:
    try:
        _maybe_send_to_broker(
            db,
            order_id=int(order_id),
            symbol=str(symbol) if symbol is not None else "",
            side=str(side) if side is not None else "",
            qty=float(qty) if qty is not None else 0.0,
            order_type=(payload.get("type") if isinstance(payload, dict) else None),
        )
    except Exception as e:
        # broker 실패는 주문 row에만 기록하고 /tv는 accepted 유지
        try:
            _set_order_status(db, int(order_id), "failed", reason=f"broker_guard: {e}")
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
"""
    indent_spaces = len(mm.group(1)) - len(mm.group(1).lstrip(" "))
    injected = "\n\n" + indent_block(broker_call.strip("\n"), indent_spaces) + "\n\n"
    src = re.sub(if_pat, injected + r"\n\1", src, count=1)

    TARGET.write_text(src, encoding="utf-8")
    print("OK: patched:", TARGET)
    print("BACKUP:", bak)

if __name__ == "__main__":
    main()
