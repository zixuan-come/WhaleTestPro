"""Bind standard {name} path parameters while retaining ${name} variables."""
import re
from urllib.parse import quote

from app.core.variables import render, render_deep


PATH_PARAMETER = re.compile(r"(?<![$\{])\{([\w-]+)\}(?!\})", re.ASCII)


def render_request_path(template, context, path_params=None):
    # Only the path has Path parameters. Query strings retain their own syntax.
    boundary = re.search(r"[?#]", template)
    end = boundary.start() if boundary else len(template)
    path, suffix = template[:end], template[end:]
    values = path_params or {}

    def replace(match):
        name = match.group(1)
        if name in values:
            value = render_deep(values[name], context)
        elif name in context:
            value = context[name]
        else:
            raise ValueError(f"请填写路径参数：{name}")
        if value is None or not str(value).strip():
            raise ValueError(f"请填写路径参数：{name}")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"路径参数 {name} 必须是文本或数值")
        if str(value) in {".", ".."}:
            raise ValueError(f"路径参数 {name} 不能是 . 或 ..")
        return quote(str(value), safe="")

    return render(PATH_PARAMETER.sub(replace, path) + suffix, context)
