from typing import Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator


class RegressionTargets(BaseModel):
    mode: Literal["suite", "case"]
    ids: list[PositiveInt] = Field(min_length=1, max_length=1000)

    @field_validator("ids")
    @classmethod
    def distinct_ids(cls, values):
        return list(dict.fromkeys(values))


class RegressionSelection(RegressionTargets):
    env_id: PositiveInt | None = None


class RegressionRun(RegressionSelection):
    preview_key: str = Field(min_length=64, max_length=64)
    notify: bool = False
