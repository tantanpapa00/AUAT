import json, os, sys

def try_load(path):
    b = open(path, "rb").read()

    # 1) UTF-16LE/BE 감지 (윈도우에서 가끔 발생)
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
        enc = "utf-16"
    else:
        # 2) UTF-8 BOM 포함 가능성 처리
        enc = "utf-8-sig"

    s = b.decode(enc, errors="strict")

    # 3) NULL(\\x00) 같은 비가시문자 제거(있으면 PS가 깨지는 경우 많음)
    s2 = s.replace("\x00", "")

    try:
        obj = json.loads(s2)
        return obj, enc, (s != s2)
    except json.JSONDecodeError as e:
        start = max(0, e.pos - 60)
        end = min(len(s2), e.pos + 60)
        snippet = s2[start:end].replace("\n", "\\n")
        raise RuntimeError(f"{path} JSON error: {e} | around: ...{snippet}...")

def dump_clean(obj, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

base = r"C:\autobot"

final_path   = os.path.join(base, "config.final.json")
default_path = os.path.join(base, "config.default.json")

# final
final_obj, final_enc, final_null_fixed = try_load(final_path)
dump_clean(final_obj, os.path.join(base, "config.final.clean.json"))

# default
default_obj, default_enc, default_null_fixed = try_load(default_path)
dump_clean(default_obj, os.path.join(base, "config.default.clean.json"))

# wrap payload (final 기준)
wrap = {"name":"final", "values": final_obj, "is_active": True}
dump_clean(wrap, os.path.join(base, "config_wrap.final.json"))

print("OK")
print("final  :", final_enc, "null_fixed" if final_null_fixed else "clean")
print("default:", default_enc, "null_fixed" if default_null_fixed else "clean")
print("wrote: config.final.clean.json, config.default.clean.json, config_wrap.final.json")
