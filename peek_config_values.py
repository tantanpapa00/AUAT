from app.db import engine
from sqlalchemy import text

config_id = 3
q = "select values from strategy_configs where id = :id"
with engine.begin() as c:
    row = c.execute(text(q), {"id": config_id}).fetchone()

vals = row[0] if row else {}
keys = ["tv_secret","instId_mode","buy1","sell_payload_mode","htf_tf"]
print({k: vals.get(k) for k in keys})
print("TOTAL_KEYS:", len(vals.keys()))
