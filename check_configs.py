from app.db import engine
from sqlalchemy import text

q = """
select id, strategy_id, name, config_hash, is_active, created_at
from strategy_configs
order by id desc
limit 5
"""
with engine.begin() as c:
    rows = c.execute(text(q)).fetchall()
print(rows)
