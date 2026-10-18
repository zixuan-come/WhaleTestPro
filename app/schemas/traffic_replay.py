from typing import Any
from pydantic import BaseModel, Field


class ReplayRequest(BaseModel):
    env_id: int | None = None              # 回放打哪个环境，不传默认本机
    field_rules: dict[str, str] | None = None  # diff 字段规则，叠加到默认规则上（C 的 b）
    headers: dict[str, str] | None = Field(default=None, max_length=100)
    params: dict[str, Any] | None = Field(default=None, max_length=100)
    body: Any = None
