# 逐字段 diff 两个响应体（智能模糊比对 C）。核心矛盾=动态字段（id/created_at/token
# 每次必不同）。给字段配规则：ignore 完全跳过 / type 只比类型 / regex 比格式 /
# range 数值容差。命中规则的字段按规则判定，没配规则的字段精确比对。纯函数，回归比对也能复用。
import re

# 规则格式 "类型:参数"：ignore（完全不比）/ type:int|str|float|bool|list|dict（只比类型）
# / regex:正则（回放值匹配格式）/ range:0.01（数值容差）。a+b 的"忽略字段"= ignore 规则。
DEFAULT_FIELD_RULES = {
    "id": "type:int",        # 自增 id 每次不同，但类型得稳定是 int（变 str 算回归 bug）
    "created_at": "type:str",
    "updated_at": "type:str",
    "token": "ignore",       # 随机 token，完全不比
}

_TYPE_MAP = {
    "int": int, "str": str, "float": (int, float),
    "bool": bool, "list": list, "dict": dict,
}


def diff_response(recorded, replayed, field_rules=None):
    # 默认规则打底 + 调用方传入的规则叠加（同名覆盖）
    rules = {**DEFAULT_FIELD_RULES, **(field_rules or {})}
    diffs = []
    _diff(recorded, replayed, "", rules, diffs)
    return {"same": not diffs, "diffs": diffs}


def _match_rule(rule, rec, rep):
    # 命中规则的字段按规则判定：符合返回 (True, None)，不符合返回 (False, 原因)
    kind, _, param = rule.partition(":")
    if kind == "ignore":
        return True, None
    if kind == "type":
        expected = _TYPE_MAP.get(param)
        if expected and isinstance(rep, expected):
            return True, None
        return False, f"类型不符:期望 {param},实际 {type(rep).__name__}"
    if kind == "regex":
        if isinstance(rep, str) and re.match(param, rep):
            return True, None
        return False, f"不匹配正则 {param}"
    if kind == "range":
        if isinstance(rec, (int, float)) and isinstance(rep, (int, float)) and abs(rec - rep) <= float(param):
            return True, None
        return False, f"超出容差 ±{param}"
    return False, f"未知规则 {rule}"


def _diff(rec, rep, path, rules, diffs):
    if isinstance(rec, dict) and isinstance(rep, dict):
        for k in set(rec) | set(rep):
            child = f"{path}.{k}" if path else k
            if k in rules:                    # 命中规则：按规则比，不递归
                ok, reason = _match_rule(rules[k], rec.get(k), rep.get(k))
                if not ok:
                    diffs.append({"path": child, "recorded": rec.get(k), "replayed": rep.get(k), "reason": reason})
                continue
            if k not in rec:
                diffs.append({"path": child, "recorded": None, "replayed": rep[k], "reason": "回放多出字段"})
            elif k not in rep:
                diffs.append({"path": child, "recorded": rec[k], "replayed": None, "reason": "回放缺失字段"})
            else:
                _diff(rec[k], rep[k], child, rules, diffs)
    elif isinstance(rec, list) and isinstance(rep, list):
        if len(rec) != len(rep):
            diffs.append({"path": path or "(root)", "recorded": rec, "replayed": rep, "reason": "列表长度不同"})
        else:
            for i, (a, b) in enumerate(zip(rec, rep)):
                _diff(a, b, f"{path}[{i}]", rules, diffs)
    elif rec != rep:
        diffs.append({"path": path or "(root)", "recorded": rec, "replayed": rep})
