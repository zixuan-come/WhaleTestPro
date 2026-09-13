import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserLogin


# ---------- 用户名长度边界 ----------
@pytest.mark.parametrize("username", ["abcd", "a" * 20])
def test_register_accept_username_length_boundaries(username):
    user = UserCreate(username=username, password="p" * 8)
    assert user.username == username


@pytest.mark.parametrize("username", ["abc", "a" * 21])
def test_register_reject_username_outside_4_to_20(username):
    with pytest.raises(ValidationError):
        UserCreate(username=username, password="p" * 8)


# ---------- 密码长度边界（现行规则：4-20）----------
@pytest.mark.parametrize("password", ["p" * 4, "p" * 20])
def test_register_accept_password_boundaries(password):
    user = UserCreate(username="abcd", password=password)
    assert user.password == password


@pytest.mark.parametrize("password", ["p" * 3, "p" * 21])
def test_register_reject_password_outside_4_to_20(password):
    with pytest.raises(ValidationError):
        UserCreate(username="abcd", password=password)


# ---------- BUG-021 账号规则（方案1 严格规则）----------
def test_register_trims_whitespace():
    user = UserCreate(username="  abcd  ", password="p" * 8)
    assert user.username == "abcd"


def test_register_lowercases_username():
    user = UserCreate(username="Alice", password="p" * 8)
    assert user.username == "alice"


@pytest.mark.parametrize(
    "username",
    ["ab_cd", "ab-cd", "user01", "a1b2c3"],
)
def test_register_accept_valid_charset(username):
    user = UserCreate(username=username, password="p" * 8)
    assert user.username == username.lower()


@pytest.mark.parametrize(
    "username",
    [
        "_abcd",        # 不能以下划线开头
        "-abcd",        # 不能以连字符开头
        "ab cd",        # 不能含空格
        "ab@cd",        # 非法字符
        "用户名test",    # 非法字符（中文）
        "abc😀",        # emoji
    ],
)
def test_register_reject_invalid_charset(username):
    with pytest.raises(ValidationError):
        UserCreate(username=username, password="p" * 8)


@pytest.mark.parametrize("username", ["1234", "00001"])
def test_register_reject_pure_digits(username):
    with pytest.raises(ValidationError):
        UserCreate(username=username, password="p" * 8)


# ---------- 登录归一化 ----------
def test_login_normalizes_username():
    login = UserLogin(username="  Alice  ", password="whatever")
    assert login.username == "alice"


def test_login_does_not_enforce_password_length():
    # 登录不应因老密码长度限制而拒绝（长度校验只在注册）
    login = UserLogin(username="abcd", password="123")
    assert login.password == "123"
