import json, re

p = r"C:\autobot\inputs.json"
b = open(p, "rb").read()
s = b.decode("utf-8-sig")
j = json.loads(s)

# 한글이 포함된 title/group_name/tooltip 샘플 10개 출력
cnt = 0
for it in j.get("inputs", []):
    t = (it.get("title") or "") + " " + (it.get("group") or it.get("group_name") or "") + " " + (it.get("tooltip") or "")
    if re.search(r"[가-힣]", t):
        print("KEY:", it.get("key"))
        print("TITLE:", it.get("title"))
        print("GROUP:", it.get("group") or it.get("group_name"))
        print("TOOLTIP:", it.get("tooltip"))
        print("-"*40)
        cnt += 1
        if cnt >= 10: break

print("TOTAL inputs:", len(j.get("inputs", [])))
