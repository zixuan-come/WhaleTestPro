"""Declarative HTTP load plans. No Python, SQL or executable scripts."""
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from jsonpath_ng import parse
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_path(value: str) -> str:
    value = value.strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise ValueError("请求路径必须是以单个 / 开头的相对路径")
    if any(ord(char) < 32 for char in value) or urlsplit(value).netloc:
        raise ValueError("请求路径包含非法字符")
    return value


class PerfAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["json_eq", "json_contains", "json_gt", "json_lt",
                  "header_eq", "header_contains", "response_time_lt", "json_schema"]
    path: str | None = Field(default=None, max_length=1000)
    expected: Any

    @model_validator(mode="after")
    def check_path(self):
        if self.type == "json_schema":
            def reject_remote(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                            raise ValueError("压测 JSON Schema 只允许本地引用，不允许外部网络读取")
                        reject_remote(item)
                elif isinstance(value, list):
                    for item in value:
                        reject_remote(item)
            reject_remote(self.expected)
            try:
                Draft202012Validator.check_schema(self.expected)
            except Exception:
                raise ValueError("JSON Schema 格式无效") from None
        if self.type.startswith("json_") and self.type != "json_schema":
            if not self.path:
                raise ValueError("JSON 断言需要 JSONPath")
            try:
                parse(self.path)
            except Exception:
                raise ValueError("JSONPath 格式无效") from None
        if self.type.startswith("header_") and not self.path:
            raise ValueError("Header 断言需要字段名")
        if self.type == "response_time_lt" and (
            type(self.expected) not in (int, float) or self.expected <= 0
        ):
            raise ValueError("响应时间阈值必须是正数（毫秒）")
        return self


class PerfStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="请求", min_length=1, max_length=100)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = Field(min_length=1, max_length=1000)
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body_type: Literal["none", "json", "form", "raw"] = "none"
    body: Any = None
    expected_status: int | None = Field(default=None, ge=100, le=599)
    extract_rules: dict[str, str] = Field(default_factory=dict)
    assertions: list[PerfAssertion] = Field(default_factory=list, max_length=50)
    allow_redirects: bool = False

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("path")
    @classmethod
    def check_path(cls, value):
        return validate_path(value)

    @field_validator("headers")
    @classmethod
    def check_headers(cls, value):
        for key, item in value.items():
            if not key or any(char in key + item for char in "\r\n"):
                raise ValueError("请求头名称不能为空，且不能包含换行")
        return value

    @field_validator("extract_rules")
    @classmethod
    def check_extract_rules(cls, value):
        if len(value) > 50:
            raise ValueError("每步最多 50 条变量提取")
        for name, path in value.items():
            if not re.fullmatch(r"\w+", name) or name.startswith("_vu_") or name == "_iteration":
                raise ValueError("变量名仅允许字母、数字、下划线，不能使用保留变量")
            if len(path) > 1000:
                raise ValueError("JSONPath 过长")
            try:
                parse(path)
            except Exception:
                raise ValueError("提取规则 JSONPath 格式无效") from None
        return value

    @model_validator(mode="after")
    def check_body(self):
        if self.body_type == "none" and self.body is not None:
            raise ValueError("无请求体模式不能携带 body")
        if self.body_type == "form" and not isinstance(self.body, dict):
            raise ValueError("表单请求体必须是对象")
        if self.body_type == "raw" and not isinstance(self.body, str):
            raise ValueError("原始请求体必须是字符串")
        return self


class PerfLoadConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["single", "chain"] = "single"
    steps: list[PerfStep] = Field(min_length=1, max_length=100)
    variables: dict[str, Any] = Field(default_factory=dict)
    datasets: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    stop_on_failure: bool = True
    timeout_seconds: float = Field(default=30, ge=0.1, le=120)
    wait_seconds: float = Field(default=1, ge=0, le=60)

    @model_validator(mode="after")
    def check_plan(self):
        if self.mode == "single" and len(self.steps) != 1:
            raise ValueError("单接口模式只能包含一个步骤")
        for values in [self.variables, *self.datasets]:
            if any(not re.fullmatch(r"\w+", name) or name.startswith("_vu_") or name == "_iteration"
                   for name in values):
                raise ValueError("初始变量名称无效或占用了保留变量")
        try:
            serialized = json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("压测配置只能包含有限 JSON 值") from None
        if len(serialized.encode("utf-8")) > 262144:
            raise ValueError("压测配置不能超过 256 KiB")
        return self
