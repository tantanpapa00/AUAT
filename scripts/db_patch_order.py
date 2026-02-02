# db_patch_order.py (v2)
# - show: prints key fields
# - patch_recover: prepare a recover-by-clOrdId test WITHOUT changing symbol
# - patch_invalid_symbol: prepare a negative test by corrupting symbol
# - restore_symbol: restore symbol to a given value (default ETH-USDT)
#
# Usage:
#   python scripts/db_patch_order.py <order_id> show
#   python scripts/db_patch_order.py <order_id> patch_recover
#   python scripts/db_patch_order.py <order_id> patch_invalid_symbol
#   python scripts/db_patch_order.py <order_id> restore_symbol [SYMBOL]
#
import os, sys
from sqlalchemy import create_engine, text

def main():
    if len(sys.argv) < 3:
        print("Usage: db_patch_order.py <id> (show|patch_recover|patch_invalid_symbol|restore_symbol) [symbol]")
        sys.exit(1)

    oid = int(sys.argv[1])
    mode = sys.argv[2]
    sym_restore = sys.argv[3] if len(sys.argv) >= 4 else "ETH-USDT"

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing (set $env:DATABASE_URL first)")

    e = create_engine(url)

    def show(conn):
        row = conn.execute(text("""
            select id, symbol, submit_status, okx_order_id, submit_try_count, next_submit_at, status, reason
              from orders where id=:id
        """), {"id": oid}).mappings().first()
        print(dict(row) if row else None)

    def patch_common(conn, corrupt_symbol: bool):
        # NOTE: do NOT touch symbol unless corrupt_symbol=True
        sql = """
            update orders
               set submit_status='submit_failed',
                   status='received',
                   okx_order_id=null,
                   submit_try_count=0,
                   next_submit_at=now(),
                   submit_err=null,
                   reason=null
             where id=:id
        """
        conn.execute(text(sql), {"id": oid})
        if corrupt_symbol:
            conn.execute(text("update orders set symbol=:sym where id=:id"), {"id": oid, "sym": sym_restore + "-INVALID"})

    with e.begin() as conn:
        if mode == "show":
            show(conn)
            return
        if mode == "patch_recover":
            patch_common(conn, corrupt_symbol=False)
            print("OK: patch_recover order", oid)
            show(conn)
            return
        if mode == "patch_invalid_symbol":
            patch_common(conn, corrupt_symbol=True)
            print("OK: patch_invalid_symbol order", oid)
            show(conn)
            return
        if mode == "restore_symbol":
            conn.execute(text("update orders set symbol=:sym where id=:id"), {"id": oid, "sym": sym_restore})
            print("OK: restored symbol", oid, sym_restore)
            show(conn)
            return

        raise RuntimeError("Unknown mode: " + mode)

if __name__ == "__main__":
    main()
