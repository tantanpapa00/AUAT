import shutil
from datetime import datetime
from pathlib import Path

INDEX = Path(r"C:\autobot\app\templates\index.html")

def backup(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    b = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, b)
    return b

def replace_once(src: str, old: str, new: str) -> str:
    if old not in src:
        return src
    return src.replace(old, new, 1)

def main():
    src = INDEX.read_text(encoding="utf-8", errors="replace")
    b = backup(INDEX)
    print("Backup:", b)

    # Accounts
    src2 = replace_once(
        src,
        "    state.accounts = rows.items || [];",
        "    const arr = Array.isArray(rows) ? rows : (rows.items || []);\n    state.accounts = arr;"
    )

    # Strategies
    src2 = replace_once(
        src2,
        "    state.strategies = rows.items || [];",
        "    const arr = Array.isArray(rows) ? rows : (rows.items || []);\n    state.strategies = arr;"
    )

    # Assets
    src2 = replace_once(
        src2,
        "    state.assets = rows.items || [];",
        "    const arr = Array.isArray(rows) ? rows : (rows.items || []);\n    state.assets = arr;"
    )

    INDEX.write_text(src2, encoding="utf-8")
    print("Patched:", INDEX)

if __name__ == "__main__":
    main()
