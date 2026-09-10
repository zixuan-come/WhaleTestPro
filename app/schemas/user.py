import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    username: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=8, max_length=20)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """
        账号规则（BUG-021 方案1：严格规则）：
        - 自动 trim 首尾空格
        - 仅允许：字母、数字、下划线、连字符
        - 长度：4-20 个字符
        - 必须以字母或数字开头
        - 大小写不敏感（统一转小写）
        """
        # 自动 trim
        value = value.strip()

        # 长度检查（Pydantic Field 已做，这里再确认）
        if len(value) < 4 or len(value) > 20:
            raise ValueError("用户名长度必须在 4-20 个字符之间")

        # 字符集和格式检查
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", value):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符，且必须以字母或数字开头")

        # 不允许纯数字
        if value.isdigit():
            raise ValueError("用户名不能为纯数字")

        # 统一转小写（大小写不敏感）
        return value.lower()


class UserLogin(UserBase):
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """登录时也进行 trim 和小写转换"""
        return value.strip().lower()


class UserOut(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"