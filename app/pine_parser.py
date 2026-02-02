# app/pine_parser.py
import re
import ast
from typing import Any, Dict, List, Tuple

SUPPORTED = {"int", "float", "bool", "string", "timeframe", "source"}

def _strip_comments(text: str) -> str:
    """
    Pine 주석 제거:
    - // 라인 주석
    - /* */ 블록 주석
    문자열(" ", ' ') 내부는 건드리지 않음
    """
    out = []
    i = 0
    n = len(text)
    in_str = None
    esc = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue

        # 문자열 시작
        if ch in ('"', "'"):
            in_str = ch
            out.append(ch)
            i += 1
            continue

        # // 라인 주석
        if ch == "/" and nxt == "/":
            # 줄 끝까지 스킵 (개행은 유지)
            while i < n and text[i] != "\n":
                i += 1
            continue

        # /* */ 블록 주석
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2  # */ 소비
            continue

        out.append(ch)
        i += 1

    return "".join(out)

def _build_group_map(pine: str) -> Dict[str, str]:
    """
    const string group_x = "01. 공통" 형태를 매핑해서
    group=group_x 로 들어오면 실제 문자열로 치환한다.
    """
    out: Dict[str, str] = {}
    rx = re.compile(
        r'(?m)^\s*(?:const\s+)?string\s+([A-Za-z_]\w*)\s*=\s*("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\')\s*;?\s*$'
    )
    for m in rx.finditer(pine):
        name = m.group(1)
        lit = m.group(2)
        try:
            out[name] = ast.literal_eval(lit)
        except Exception:
            out[name] = lit.strip('"\'')
    return out

def _find_balanced_call(text: str, start_paren: int) -> Tuple[str, int]:
    """
    start_paren 위치가 '('일 때, 괄호 밸런스로 호출부를 잘라낸다.
    문자열 내부 괄호는 무시한다.
    """
    if start_paren < 0 or start_paren >= len(text) or text[start_paren] != "(":
        raise ValueError("Invalid start_paren for balanced call")

    i = start_paren
    depth = 0
    in_str = None
    esc = False

    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'"):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[start_paren:i + 1], i + 1
        i += 1

    raise ValueError("Unbalanced parentheses in input() call")

def _split_top_args(s: str) -> List[str]:
    """
    최상위 콤마 기준 분리 (문자열/괄호/배열/중괄호 안 콤마는 무시)
    """
    args: List[str] = []
    buf: List[str] = []
    dp = db = dc = 0
    in_str = None
    esc = False

    for ch in s:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            continue

        if ch in ('"', "'"):
            in_str = ch
            buf.append(ch)
            continue

        if ch == "(":
            dp += 1
        elif ch == ")":
            dp -= 1
        elif ch == "[":
            db += 1
        elif ch == "]":
            db -= 1
        elif ch == "{":
            dc += 1
        elif ch == "}":
            dc -= 1

        if ch == "," and dp == 0 and db == 0 and dc == 0:
            a = "".join(buf).strip()
            if a:
                args.append(a)
            buf = []
        else:
            buf.append(ch)

    last = "".join(buf).strip()
    if last:
        args.append(last)
    return args

def _parse_value(v: str, group_map: Dict[str, str]) -> Any:
    t = v.strip()

    if t.lower() in ("true", "false"):
        return t.lower() == "true"

    # 문자열 리터럴
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        try:
            return ast.literal_eval(t)
        except Exception:
            return t.strip('"\'')
    # 배열 리터럴
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return []
        items = _split_top_args(inner)
        return [_parse_value(x, group_map) for x in items]

    # 숫자
    if re.fullmatch(r"[+-]?\d+", t):
        return int(t)
    if re.fullmatch(r"[+-]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", t):
        return float(t)

    # group 별칭
    if t in group_map:
        return group_map[t]

    # 나머지는 식/식별자 그대로
    return t

def parse_pine_inputs(pine: str) -> Dict[str, Any]:
    # 1) 주석 제거(주석 안 input.* 오탐 방지)
    pine = _strip_comments(pine)

    # 2) 그룹 라벨 매핑
    group_map = _build_group_map(pine)

    results: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # input.xxx( 위치 찾기
    for m in re.finditer(r"\binput\.(int|float|bool|string|timeframe|source)\s*\(", pine):
        itype = m.group(1)
        if itype not in SUPPORTED:
            continue

        # 같은 줄에서 lhs 추정: x = input.xxx(
        line_start = pine.rfind("\n", 0, m.start()) + 1
        line_end = pine.find("\n", m.start())
        if line_end == -1:
            line_end = len(pine)
        line = pine[line_start:line_end]

        lhs = None
        mm = re.search(rf"^\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*=\s*input\.{itype}\s*\(", line)
        if mm:
            lhs = mm.group(1)
        else:
            lhs = f"input_{len(results)+1}"
            warnings.append(f"missing_lhs_at:{m.start()} -> key={lhs}")

        # 괄호 밸런스로 호출부 추출
        call, _ = _find_balanced_call(pine, m.end() - 1)
        inner = call[1:-1].strip()
        args = _split_top_args(inner)

        named: Dict[str, str] = {}
        positional: List[str] = []
        for a in args:
            if "=" in a:
                k, rest = a.split("=", 1)
                named[k.strip()] = rest.strip()
            else:
                positional.append(a)

        # title/defval 파싱
        title = _parse_value(named["title"], group_map) if "title" in named else None
        defval = (
            _parse_value(named["defval"], group_map)
            if "defval" in named
            else (_parse_value(positional[0], group_map) if positional else None)
        )

        # 일부 input.*는 (defval, title) 형태로도 들어옴
        if title is None and len(positional) >= 2:
            title = _parse_value(positional[1], group_map)

        out: Dict[str, Any] = {"key": lhs, "type": itype}
        if title is not None:
            out["title"] = title
        if defval is not None:
            out["defval"] = defval

        # 공통 옵션들
        for k in ("minval", "maxval", "step", "tooltip", "inline"):
            if k in named:
                out[k] = _parse_value(named[k], group_map)

        # options
        if "options" in named:
            out["options"] = _parse_value(named["options"], group_map)

        # group
        if "group" in named:
            out["group"] = _parse_value(named["group"], group_map)

        # timeframe은 문자열로 통일
        if itype == "timeframe" and "defval" in out and isinstance(out["defval"], (int, float)):
            out["defval"] = str(out["defval"])

        results.append(out)

    # key 중복 경고
    seen = set()
    for r in results:
        if r["key"] in seen:
            warnings.append(f"duplicate_key:{r['key']}")
        seen.add(r["key"])

    return {"inputs": results, "warnings": warnings, "count": len(results)}
