import re
from pathlib import Path

path = Path(r"C:\autobot\app\main.py")
src = path.read_text(encoding="utf-8", errors="replace")

# 1) bar_ts 라인: bar_ts = payload.get("bar_ts") or payload.get("time") or payload.get("timestamp")
#    -> 스펙대로 분리: bar_ts / evt_ms / bucket
src2 = src

# 첫 번째(INSERT 전) 구간 패치
src2 = re.sub(
    r'(?m)^\s*bar_ts\s*=\s*payload\.get\("bar_ts"\)\s*or\s*payload\.get\("time"\)\s*or\s*payload\.get\("timestamp"\)\s*$',
    '            bar_ts = payload.get("bar_ts")\n'
    '            evt_ms = payload.get("time")\n'
    '            bucket = str(bar_ts) if bar_ts is not None else (str(evt_ms) if evt_ms is not None else datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))',
    src2,
    count=1
)

# 두 번째(IntegrityError 후 재계산) 구간 패치
src2 = re.sub(
    r'(?m)^\s*bar_ts\s*=\s*payload\.get\("bar_ts"\)\s*or\s*payload\.get\("time"\)\s*or\s*payload\.get\("timestamp"\)\s*$',
    '            bar_ts = payload.get("bar_ts")\n'
    '            evt_ms = payload.get("time")\n'
    '            bucket = str(bar_ts) if bar_ts is not None else (str(evt_ms) if evt_ms is not None else datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))',
    src2,
    count=1
)

# 2) 기존 bucket 라인 제거(두 군데): bucket = datetime.now... if not bar_ts else str(bar_ts)
src2 = re.sub(
    r'(?m)^\s*bucket\s*=\s*datetime\.now\(timezone\.utc\)\.strftime\("%Y%m%d%H%M"\)\s*if\s*not\s*bar_ts\s*else\s*str\(bar_ts\)\s*$',
    '',
    src2
)

# 3) idem_key 계산에서 alert_id 제거 (두 군데)
src2 = re.sub(
    r'(?m)^\s*idem_key\s*=\s*_mk_idem_key\(\s*config_hash\s*,\s*alert_id\s*,\s*symbol\s*,\s*side\s*,\s*bucket\s*\)\s*$',
    '        idem_key = _mk_idem_key(config_hash, symbol, side, bucket)',
    src2
)

# 결과 검증: alert_id 포함 호출이 남아있으면 실패
if re.search(r"_mk_idem_key\(\s*config_hash\s*,\s*alert_id", src2):
    raise SystemExit("ERR: alert_id still used in _mk_idem_key call")

path.write_text(src2, encoding="utf-8")
print("OK: patched bucket rule + removed alert_id from idem_key (2 places)")
