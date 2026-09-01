import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


@pytest.mark.parametrize("username", ["abcd", "a" * 20])
def test_register_credentials_accept_username_boundaries(username):
    user = UserCreate(username=username, password="p" * 4)
    assert user.username == username


@pytest.mark.parametrize("username", ["abc", "a" * 21])
def test_register_credentials_reject_username_outside_4_to_20(username):
    with pytest.raises(ValidationError):
        UserCreate(username=username, password="p" * 4)


@pytest.mark.parametrize("password", ["p" * 4, "p" * 20])
def test_register_credentials_accept_password_boundaries(password):
    user = UserCreate(username="abcd", password=password)
    assert user.password == password


@pytest.mark.parametrize("password", ["p" * 3, "p" * 21])
def test_register_credentials_reject_password_outside_4_to_20(password):
    with pytest.raises(ValidationError):
        UserCreate(username="abcd", password=password)