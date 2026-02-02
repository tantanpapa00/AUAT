import os
import argparse
from sqlalchemy import create_engine, text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order-id", type=int, required=True)
    args = ap.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is not set (.env)")

    engine = create_engine(db_url)

    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, symbol, okx_order_id, okx_clord_id, payload_json,
                   status, submit_status, okx_state, exch_status, filled_qty, avg_px
            FROM orders WHERE id=:id
        """), {"id": args.order_id}).mappings().first()

        if not row:
            raise SystemExit(f"order not found: {args.order_id}")

        # symbol 고의 파손(표시/의존성 테스트)
        sym = row["symbol"] or ""
        bad_symbol = sym if sym.endswith("-INVALID") else (sym + "-INVALID")

        # **중요**: filled 흔적 제거 → send-now가 filled_wins_skip로 튀지 않고 recover 경로를 타게 함
        conn.execute(text("""
            UPDATE orders
            SET symbol           = :bad_symbol,

                okx_order_id     = NULL,
                okx_response     = NULL,
                exchange_order_id= NULL,
                exchange_raw     = NULL,

                okx_state        = 'unknown',
                exch_status      = 'unknown',
                filled_qty       = NULL,
                avg_px           = NULL,

                status           = 'failed',
                submit_status    = 'submit_failed',
                submit_err       = 'forced_recover_test_v2',
                reason           = 'forced_recover_test_v2',

                submit_try_count = 0,
                next_submit_at   = NOW()
            WHERE id=:id
        """), {"id": args.order_id, "bad_symbol": bad_symbol})

        after = conn.execute(text("""
            SELECT id, symbol, okx_order_id, okx_clord_id, payload_json,
                   status, submit_status, okx_state, exch_status,
                   filled_qty, avg_px, submit_err, next_submit_at, submit_try_count
            FROM orders WHERE id=:id
        """), {"id": args.order_id}).mappings().first()

        print("patched_for_recover_v2:", dict(after))

if __name__ == "__main__":
    main()
