import re
from jsonpath_ng import parse

def render(text: str, context: dict) -> str:
    def _replace(match):
        name = match.group(1)
        if name not in context:
            raise KeyError(f"变量未找到: {name}")
        return str(context[name])
    return re.sub(r"\$\{(\w+)\}", _replace, text)


def extract(data: dict, path: str):
    expr = parse(path)
    matches = expr.find(data)
    if not matches:
        raise KeyError(f"路径未找到: {path}")
    value = matches[0].value
    return value


def render_deep(obj, context):
    if isinstance(obj, str):
        return render(obj, context)
    if isinstance(obj, dict):
        return {k: render_deep(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render_deep(v, context) for v in obj]
    return obj


