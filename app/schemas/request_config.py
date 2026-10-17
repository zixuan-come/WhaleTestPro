from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr


PathParameterValues = dict[str, StrictStr | StrictInt | StrictFloat | StrictBool | None]


class RequestOverrides(BaseModel):
    """Present fields replace defaults; omitted fields inherit the interface."""
    model_config = ConfigDict(extra="forbid")
    path_params: PathParameterValues | None = None
    headers: dict | None = None
    params: dict | None = None
    body: dict | None = None
