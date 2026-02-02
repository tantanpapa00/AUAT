from app.db import engine
from sqlalchemy import text

q = """
select table_schema, table_name
from information_schema.tables
where table_schema='public'
  and table_name in ('signal_params','strategy_configs')
order by table_name
"""

with engine.begin() as c:
    rows = c.execute(text(q)).fetchall()

print(rows)
