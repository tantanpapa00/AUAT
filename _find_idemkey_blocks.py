import re
p = r"C:\autobot\app\main.py"
lines = open(p, encoding="utf-8", errors="replace").read().splitlines()

# 후보 라인: idem_key = ... / hashlib / sha256 / dedup_key = ... 가 있는 곳
hits = []
for i, line in enumerate(lines):
    if re.search(r"\bidem_key\b\s*=", line) or "sha256" in line or "hashlib" in line:
        hits.append(i)

print("HITS:", len(hits))
for k, i in enumerate(hits[:20], 1):
    s = max(0, i-6)
    e = min(len(lines), i+14)
    print(f"\n--- HIT {k} @ line {i+1} ---")
    for j in range(s, e):
        print(f"{j+1:04d}: {lines[j]}")
