from app.db import engine
from sqlalchemy import text

sid = 2

# 1) 어떤 hash가 중복인지 확인
q1 = """
select strategy_id, config_hash, count(*) as cnt, array_agg(id order by id desc) as ids
from strategy_configs
where strategy_id = :sid
group by strategy_id, config_hash
having count(*) > 1
order by cnt desc
"""
with engine.begin() as c:
    rows = c.execute(text(q1), {"sid": sid}).fetchall()

print("DUPLICATES:", rows)

# 2) 각 hash마다 최신 1개만 남기고 나머지 삭제
for (strategy_id, h, cnt, ids) in rows:
    keep_id = ids[0]        # desc 정렬이므로 첫번째가 최신
    del_ids = ids[1:]       # 나머지 삭제
    if del_ids:
        cdel = text("delete from strategy_configs where id = any(:ids)")
        with engine.begin() as c:
            c.execute(cdel, {"ids": del_ids})
        print(f"hash={h} keep={keep_id} deleted={del_ids}")

print("DONE")
