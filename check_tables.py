from app.db import engine
from sqlalchemy import text

q = \"\"\"
select tablename
from pg_tables
where schemaname = 'public'
  and tablename in ('signal_params','strategy_configs')
order by tablename
\"\"\"

with engine.begin() as c:
    rows = c.execute(text(q)).fetchall()
print(rows)
