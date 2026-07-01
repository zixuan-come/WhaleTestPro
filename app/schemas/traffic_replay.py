from pydantic import BaseModel


class ReplayRequest(BaseModel):
    env_id: int | None = None              # 回放打哪个环境，不传默认本机
    field_rules: dict[str, str] | None = None  # diff 字段规则，叠加到默认规则上（C 的 b）
