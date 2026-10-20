# 逐字段 diff 两个响应体（智能模糊比对 C）。核心矛盾=动态字段（id/created_at/token
# 每次必不同）。给字段配规则：ignore 完全跳过 / type 只比类型 / regex 比格式 /
# range 数值容差。命中规则的字段按规则判定，没配规则的字段精确比对。纯函数，回归比对也能复用。
import math
from functools import lru_cache
from time import monotonic

import regex

REGEX_BUDGET_SECONDS = 0.1
MAX_FIELD_RULES = 100
MAX_RULE_LENGTH = 1000

# 规则格式 "类型:参数"：ignore（完全不比）/ type:int|str|float|bool|list|dict（只比类型）
# / regex:正则（回放值匹配格式）/ range:0.01（数值容差）。a+b 的"忽略字段"= ignore 规则。
DEFAULT_FIELD_RULES = {
    "id": "type:int",        # 自增 id 每次不同，但类型得稳定是 int（变 str 算回归 bug）
    "created_at": "type:str",
    "updated_at": "type:str",
    "token": "ignore",       # 随机 token，完全不比
}

_TYPE_MAP = {
    "int": (int,), "str": (str,), "float": (int, float),
    "bool": (bool,), "list": (list,), "dict": (dict,),
}


@lru_cache(maxsize=256)
def _compile_regex(pattern):
    return regex.compile(pattern)


def validate_field_rules(field_rules):
    """Validate before replay sends a potentially mutating HTTP request."""
    if field_rules is None:
        return
    if not isinstance(field_rules, dict) or len(field_rules) > MAX_FIELD_RULES:
        raise ValueError("响应比较规则最多支持 100 项")
    for field, rule in field_rules.items():
        if not isinstance(field, str) or not field or len(field) > 200:
            raise ValueError("比较规则字段名须为 1～200 个字符")
        if not isinstance(rule, str) or len(rule) > MAX_RULE_LENGTH:
            raise ValueError("每条响应比较规则不能超过 1000 个字符")
        kind, _, param = rule.partition(":")
        if kind == "ignore" and not param:
            continue
        if kind == "type" and param in _TYPE_MAP:
            continue
        if kind == "regex":
            try:
                _compile_regex(param)
            except (regex.error, RecursionError):
                raise ValueError("响应比较规则中的正则表达式无效") from None
            continue
        if kind == "range":
            try:
                tolerance = float(param)
            except ValueError:
                raise ValueError("响应比较规则的数值容差须为非负有限数字") from None
            if math.isfinite(tolerance) and tolerance >= 0:
                continue
            raise ValueError("响应比较规则的数值容差须为非负有限数字")
        raise ValueError("响应比较规则类型无效")


def diff_response(recorded, replayed, field_rules=None):
    # 默认规则打底 + 调用方传入的规则叠加（同名覆盖）
    validate_field_rules(field_rules)
    rules = {**DEFAULT_FIELD_RULES, **(field_rules or {})}
    diffs = []
    # One budget for the whole comparison, rather than one timeout per field.
    _diff(recorded, replayed, "", rules, diffs, monotonic() + REGEX_BUDGET_SECONDS)
    return {"same": not diffs, "diffs": diffs}


def _match_rule(rule, rec, rep, regex_deadline=None):
    # 命中规则的字段按规则判定：符合返回 (True, None)，不符合返回 (False, 原因)
    kind, _, param = rule.partition(":")
    if kind == "ignore":
        return True, None
    if kind == "type":
        expected = _TYPE_MAP.get(param)
        if expected and type(rep) in expected:
            return True, None
        return False, f"类型不符:期望 {param},实际 {type(rep).__name__}"
    if kind == "regex":
        if isinstance(rep, str):
            remaining = (regex_deadline - monotonic()) if regex_deadline is not None else REGEX_BUDGET_SECONDS
            if remaining <= 0:
                return False, "正则比较时间已超过上限"
            try:
                if _compile_regex(param).match(rep, timeout=remaining, concurrent=True):
                    return True, None
            except TimeoutError:
                return False, "正则比较时间已超过上限"
        return False, f"不匹配正则 {param}"
    if kind == "range":
        if type(rec) in (int, float) and type(rep) in (int, float) and abs(rec - rep) <= float(param):
            return True, None
        return False, f"超出容差 ±{param}"
    return False, f"未知规则 {rule}"


def _diff(rec, rep, path, rules, diffs, regex_deadline=None):
    if isinstance(rec, dict) and isinstance(rep, dict):
        for k in set(rec) | set(rep):
            child = f"{path}.{k}" if path else k
            if k in rules:                    # 命中规则：按规则比，不递归
                ok, reason = _match_rule(rules[k], rec.get(k), rep.get(k), regex_deadline)
                if not ok:
                    diffs.append({"path": child, "recorded": rec.get(k), "replayed": rep.get(k), "reason": reason})
                continue
            if k not in rec:
                diffs.append({"path": child, "recorded": None, "replayed": rep[k], "reason": "回放多出字段"})
            elif k not in rep:
                diffs.append({"path": child, "recorded": rec[k], "replayed": None, "reason": "回放缺失字段"})
            else:
                _diff(rec[k], rep[k], child, rules, diffs, regex_deadline)
    elif isinstance(rec, list) and isinstance(rep, list):
        if len(rec) != len(rep):
            diffs.append({"path": path or "(root)", "recorded": rec, "replayed": rep, "reason": "列表长度不同"})
        else:
            for i, (a, b) in enumerate(zip(rec, rep)):
                _diff(a, b, f"{path}[{i}]", rules, diffs, regex_deadline)
    elif isinstance(rec, bool) != isinstance(rep, bool) or rec != rep:
        diffs.append({"path": path or "(root)", "recorded": rec, "replayed": rep})
