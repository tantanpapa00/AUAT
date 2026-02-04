# CUSTOM_RULE_SPEC.md (SSOT)
- Last updated: 2026-02-04 KST
- Owner: 기훈(작가님)
- Status: Week 16 Day 1

> NOTE: 이 파일은 커스텀 Rule Builder의 '진실(SSOT)'입니다.
> Premium 신호 정의는 docs/PREMIUM_SIGNALS.md 참조.

---

# 1) 개요

커스텀 Rule Builder는 사용자가 지표 조합으로 자신만의 매매 규칙을 생성할 수 있는 기능입니다.

## 1-1) 원칙

| 허용 | 금지 |
|------|------|
| 지원 인디케이터 조합 | 코드 직접 입력 |
| Entry/Exit 규칙 정의 | 무제한 복잡도 |
| 조건 그룹 (AND/OR) | 같은 레벨 AND/OR 혼합 |
| TP/SL/Trailing 설정 | 선물/레버리지 |

## 1-2) 제한 사항 (v1)

- 지원 인디케이터: 6종으로 제한
- 복잡도 제한: 깊이 3, 총 leaf 12개
- Rule Lint: 희소/상충 조건 경고
- TF 정책: 15분봉 이상 권장

---

# 2) 지원 인디케이터 (v1)

## 2-1) 인디케이터 목록

| 인디케이터 | 코드 | 파라미터 | 출력값 |
|------------|------|----------|--------|
| 이동평균 | MA | period, type(SMA/EMA/WMA) | value |
| 볼린저밴드 | BB | period, std_mult | upper, middle, lower, %b |
| RSI | RSI | period | value (0-100) |
| MACD | MACD | fast, slow, signal | macd, signal, histogram |
| CCI | CCI | period | value |
| 일목균형표 | ICHIMOKU | tenkan, kijun, senkou | tenkan, kijun, senkou_a, senkou_b, chikou |

## 2-2) 인디케이터 스키마

```python
class IndicatorDef(BaseModel):
    """인디케이터 정의"""
    code: str                    # MA, BB, RSI, MACD, CCI, ICHIMOKU
    params: Dict[str, Any]       # 파라미터
    output: str                  # 사용할 출력값 (e.g., "upper", "value")

# 예시
{
    "code": "RSI",
    "params": {"period": 14},
    "output": "value"
}

{
    "code": "BB",
    "params": {"period": 20, "std_mult": 2.0},
    "output": "lower"
}

{
    "code": "MA",
    "params": {"period": 50, "type": "EMA"},
    "output": "value"
}
```

## 2-3) 파라미터 범위

| 인디케이터 | 파라미터 | 최소 | 최대 | 기본값 |
|------------|----------|------|------|--------|
| MA | period | 2 | 500 | 20 |
| MA | type | - | - | SMA |
| BB | period | 5 | 200 | 20 |
| BB | std_mult | 0.5 | 5.0 | 2.0 |
| RSI | period | 2 | 100 | 14 |
| MACD | fast | 2 | 100 | 12 |
| MACD | slow | 5 | 200 | 26 |
| MACD | signal | 2 | 50 | 9 |
| CCI | period | 5 | 200 | 20 |
| ICHIMOKU | tenkan | 5 | 100 | 9 |
| ICHIMOKU | kijun | 10 | 200 | 26 |
| ICHIMOKU | senkou | 20 | 500 | 52 |

---

# 3) 비교 연산자

## 3-1) 지원 연산자

| 연산자 | 코드 | 설명 | 예시 |
|--------|------|------|------|
| 초과 | GT | > | RSI > 70 |
| 이상 | GTE | >= | close >= MA |
| 미만 | LT | < | RSI < 30 |
| 이하 | LTE | <= | close <= BB.lower |
| 상향돌파 | CROSS_ABOVE | 이전 < 현재 >= | close crosses above MA |
| 하향돌파 | CROSS_BELOW | 이전 > 현재 <= | close crosses below MA |

## 3-2) 피연산자 타입

| 타입 | 코드 | 설명 |
|------|------|------|
| 가격 | PRICE | open, high, low, close |
| 인디케이터 | INDICATOR | 인디케이터 출력값 |
| 상수 | CONSTANT | 숫자 상수 |

---

# 4) 조건 구조 (AST)

## 4-1) 단일 조건 (Leaf)

```python
class Condition(BaseModel):
    """단일 조건 (leaf node)"""
    left: Operand           # 좌변
    operator: str           # GT, GTE, LT, LTE, CROSS_ABOVE, CROSS_BELOW
    right: Operand          # 우변

class Operand(BaseModel):
    """피연산자"""
    type: str               # PRICE, INDICATOR, CONSTANT
    value: Any              # "close", IndicatorDef, 30.0
```

예시:
```json
{
    "left": {"type": "INDICATOR", "value": {"code": "RSI", "params": {"period": 14}, "output": "value"}},
    "operator": "LT",
    "right": {"type": "CONSTANT", "value": 30}
}
```

## 4-2) 조건 그룹 (Node)

```python
class ConditionGroup(BaseModel):
    """조건 그룹 (AND/OR)"""
    logic: str              # AND, OR
    conditions: List[Union[Condition, ConditionGroup]]
```

예시 (RSI < 30 AND close < BB.lower):
```json
{
    "logic": "AND",
    "conditions": [
        {
            "left": {"type": "INDICATOR", "value": {"code": "RSI", "params": {"period": 14}, "output": "value"}},
            "operator": "LT",
            "right": {"type": "CONSTANT", "value": 30}
        },
        {
            "left": {"type": "PRICE", "value": "close"},
            "operator": "LT",
            "right": {"type": "INDICATOR", "value": {"code": "BB", "params": {"period": 20, "std_mult": 2.0}, "output": "lower"}}
        }
    ]
}
```

---

# 5) 복잡도 제한 (v1)

## 5-1) 제한값

| 항목 | 제한 | 설명 |
|------|------|------|
| max_depth | 3 | 최대 중첩 깊이 |
| max_leaf_total | 12 | 전체 조건 노드 수 |
| max_leaf_per_group | 6 | 그룹당 조건 수 |
| max_or_groups | 2 | OR 그룹 수 |
| max_leaf_per_or_group | 4 | OR 그룹당 조건 수 |

## 5-2) 금지 규칙

- 같은 레벨에서 AND/OR 혼합 금지
- 초과 시 `rule_complexity_exceeded` 에러

## 5-3) 복잡도 검증 함수

```python
def validate_complexity(rule: ConditionGroup, depth: int = 0) -> Tuple[bool, str]:
    """
    복잡도 제한 검증
    Returns: (is_valid, error_message)
    """
    MAX_DEPTH = 3
    MAX_LEAF_TOTAL = 12
    MAX_LEAF_PER_GROUP = 6
    MAX_OR_GROUPS = 2
    MAX_LEAF_PER_OR_GROUP = 4

    # 깊이 체크
    if depth > MAX_DEPTH:
        return False, f"max_depth exceeded: {depth} > {MAX_DEPTH}"

    # 그룹당 조건 수 체크
    if len(rule.conditions) > MAX_LEAF_PER_GROUP:
        return False, f"max_leaf_per_group exceeded: {len(rule.conditions)} > {MAX_LEAF_PER_GROUP}"

    # OR 그룹 제한 체크
    if rule.logic == "OR" and len(rule.conditions) > MAX_LEAF_PER_OR_GROUP:
        return False, f"max_leaf_per_or_group exceeded"

    # 재귀적으로 하위 그룹 검증
    leaf_count = 0
    or_count = 0

    for cond in rule.conditions:
        if isinstance(cond, ConditionGroup):
            if cond.logic == "OR":
                or_count += 1
            valid, msg = validate_complexity(cond, depth + 1)
            if not valid:
                return False, msg
        else:
            leaf_count += 1

    if or_count > MAX_OR_GROUPS:
        return False, f"max_or_groups exceeded: {or_count} > {MAX_OR_GROUPS}"

    return True, ""
```

---

# 6) Rule Lint (v1)

## 6-1) Lint 등급

| 등급 | 의미 | 처리 |
|------|------|------|
| OK | 정상 | 저장/실행 허용 |
| WARN | 희소/상충 가능성 | 저장 허용 + 강한 경고 UI |
| BLOCK | 거의 불가능/위험 | 저장 불가 (premium 우회 토글) |

## 6-2) Lint 규칙

### WARN 조건

| 규칙 | 설명 | 예시 |
|------|------|------|
| RARE_COMBO | 희소한 조합 | BB.upper < close AND RSI < 30 |
| CONFLICTING_MA | MA 충돌 | close > MA(50) AND close < MA(20) |
| EXTREME_PARAMS | 극단적 파라미터 | RSI(2), MA(500) |

### BLOCK 조건

| 규칙 | 설명 | 예시 |
|------|------|------|
| CONTRADICTION | 모순 | RSI > 90 AND RSI < 10 |
| IMPOSSIBLE | 불가능한 조건 | close > high |
| ALWAYS_TRUE | 항상 참 | RSI >= 0 AND RSI <= 100 |
| ALWAYS_FALSE | 항상 거짓 | close > close |

## 6-3) Lint 검증 함수

```python
def lint_rule(rule: CustomRule) -> LintResult:
    """
    Rule Lint 수행
    Returns: LintResult(grade, warnings, blocks)
    """
    warnings = []
    blocks = []

    # Entry 조건 검사
    entry_issues = _check_conditions(rule.entry)
    warnings.extend(entry_issues.warnings)
    blocks.extend(entry_issues.blocks)

    # Exit 조건 검사
    exit_issues = _check_conditions(rule.exit)
    warnings.extend(exit_issues.warnings)
    blocks.extend(exit_issues.blocks)

    # 최종 등급 결정
    if blocks:
        grade = "BLOCK"
    elif warnings:
        grade = "WARN"
    else:
        grade = "OK"

    return LintResult(
        grade=grade,
        warnings=warnings,
        blocks=blocks,
        message=_format_lint_message(grade, warnings, blocks)
    )

def _check_contradiction(conditions: List[Condition]) -> List[str]:
    """모순 조건 검사"""
    blocks = []

    # 같은 인디케이터에 대한 충돌 검사
    indicator_conditions = {}
    for cond in conditions:
        if cond.left.type == "INDICATOR":
            key = _get_indicator_key(cond.left.value)
            if key not in indicator_conditions:
                indicator_conditions[key] = []
            indicator_conditions[key].append(cond)

    for key, conds in indicator_conditions.items():
        if len(conds) >= 2:
            # RSI > 70 AND RSI < 30 같은 모순 검사
            for i, c1 in enumerate(conds):
                for c2 in conds[i+1:]:
                    if _is_contradiction(c1, c2):
                        blocks.append(f"CONTRADICTION: {key} conditions conflict")

    return blocks
```

---

# 7) 커스텀 규칙 스키마

## 7-1) CustomRule 모델

```python
class CustomRule(BaseModel):
    """커스텀 규칙 전체"""
    rule_id: str                # 고유 ID
    rule_name: str              # 규칙 이름
    version: str = "1.0"

    # 조건
    entry: ConditionGroup       # Entry 조건
    exit: ConditionGroup        # Exit 조건

    # Exit 옵션
    exit_options: ExitOptions

    # 메타
    created_at: datetime
    updated_at: datetime

    # Lint 결과
    lint_grade: str = "OK"      # OK/WARN/BLOCK
    lint_message: Optional[str] = None

class ExitOptions(BaseModel):
    """Exit 옵션"""
    use_signal_exit: bool = True    # Exit 규칙 신호 사용
    tp_pct: Optional[float] = None  # Take Profit %
    sl_pct: Optional[float] = None  # Stop Loss %
    trailing_pct: Optional[float] = None  # Trailing Stop %
```

## 7-2) DB 스키마

```sql
CREATE TABLE IF NOT EXISTS custom_rules (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         TEXT NOT NULL UNIQUE,
    rule_name       TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '1.0',

    -- 조건 (JSON)
    entry_ast       JSONB NOT NULL,
    exit_ast        JSONB NOT NULL,

    -- Exit 옵션
    use_signal_exit BOOLEAN DEFAULT TRUE,
    tp_pct          FLOAT,
    sl_pct          FLOAT,
    trailing_pct    FLOAT,

    -- Lint
    lint_grade      TEXT NOT NULL DEFAULT 'OK',
    lint_message    TEXT,

    -- 메타
    user_id         TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_custom_rules_user ON custom_rules(user_id);
CREATE INDEX idx_custom_rules_grade ON custom_rules(lint_grade);
```

---

# 8) API 엔드포인트

## 8-1) 규칙 생성

```
POST /api/custom/rules
Content-Type: application/json

{
    "rule_name": "RSI 역추세 v1",
    "entry": { ... },      // ConditionGroup
    "exit": { ... },       // ConditionGroup
    "exit_options": {
        "use_signal_exit": true,
        "tp_pct": 5.0,
        "sl_pct": 3.0
    }
}

Response (성공):
{
    "ok": true,
    "rule_id": "rule_abc123",
    "lint_grade": "OK",
    "lint_message": null
}

Response (복잡도 초과):
{
    "ok": false,
    "code": "rule_complexity_exceeded",
    "detail": "max_depth exceeded: 4 > 3"
}

Response (Lint BLOCK):
{
    "ok": false,
    "code": "rule_lint_block",
    "detail": "CONTRADICTION: RSI conditions conflict",
    "lint_grade": "BLOCK",
    "lint_warnings": [],
    "lint_blocks": ["CONTRADICTION: RSI > 90 AND RSI < 10"]
}
```

## 8-2) 규칙 검증 (미리보기)

```
POST /api/custom/rules/validate
Content-Type: application/json

{
    "entry": { ... },
    "exit": { ... }
}

Response:
{
    "ok": true,
    "complexity": {
        "depth": 2,
        "leaf_count": 5,
        "or_groups": 1
    },
    "lint": {
        "grade": "WARN",
        "warnings": ["RARE_COMBO: BB.upper < close AND RSI < 30"],
        "blocks": []
    }
}
```

## 8-3) 규칙 목록

```
GET /api/custom/rules?user_id={id}&lint_grade={grade}

Response:
{
    "ok": true,
    "rules": [
        {
            "rule_id": "rule_abc123",
            "rule_name": "RSI 역추세 v1",
            "lint_grade": "OK",
            "is_active": true,
            "created_at": "2026-02-04T12:00:00Z"
        }
    ],
    "total": 1
}
```

## 8-4) 규칙 상세

```
GET /api/custom/rules/{rule_id}

Response:
{
    "ok": true,
    "rule": {
        "rule_id": "rule_abc123",
        "rule_name": "RSI 역추세 v1",
        "entry": { ... },
        "exit": { ... },
        "exit_options": { ... },
        "lint_grade": "OK",
        "created_at": "2026-02-04T12:00:00Z"
    }
}
```

---

# 9) 에러 코드

| 코드 | HTTP | 의미 |
|------|------|------|
| `rule_complexity_exceeded` | 400 | 복잡도 제한 초과 |
| `rule_lint_block` | 400 | Lint BLOCK |
| `invalid_indicator` | 400 | 지원하지 않는 인디케이터 |
| `invalid_operator` | 400 | 지원하지 않는 연산자 |
| `invalid_params` | 400 | 파라미터 범위 초과 |
| `rule_not_found` | 404 | 규칙 없음 |
| `custom_disabled` | 403 | 커스텀 비활성화 |

---

# 10) 참조

- docs/PREMIUM_SIGNALS.md (§5 커스텀 신호 정의)
- docs/PREMIUM_ENGINE_SPEC.md (Premium 입출력)
- docs/PROJECT_STATUS.md (일정)

---

[END OF CUSTOM_RULE_SPEC]
