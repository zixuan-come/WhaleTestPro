from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

ReportReference = Annotated[str, Field(pattern=r"^(run|legacy|scenario)-[1-9][0-9]*$", max_length=40)]


class ReportFolderName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_ids: list[ReportReference] = Field(min_length=1, max_length=500)

    @field_validator("report_ids")
    @classmethod
    def unique_ids(cls, value):
        return list(dict.fromkeys(value))


class ReportMove(ReportSelection):
    folder_id: int | None = Field(default=None, ge=1)


class ReportFolderOut(BaseModel):
    id: int
    name: str
    count: int


class ReportFolderPage(BaseModel):
    items: list[ReportFolderOut]
    total: int
    unfiled: int
    can_manage: bool
