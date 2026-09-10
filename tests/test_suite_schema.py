import pytest
from pydantic import ValidationError
from app.schemas.suite import SuiteCreate, SuiteUpdate


def test_suite_create_validates_name_length():
    with pytest.raises(ValidationError):
        SuiteCreate(name="", type="case")


def test_suite_create_validates_name_whitespace():
    with pytest.raises(ValidationError, match="不能为空或纯空格"):
        SuiteCreate(name="   ", type="case")


def test_suite_create_validates_description_length():
    with pytest.raises(ValidationError):
        SuiteCreate(name="suite", description="x" * 501, type="case")


def test_suite_create_validates_type_enum():
    with pytest.raises(ValidationError):
        SuiteCreate(name="suite", type="invalid")


def test_suite_create_accepts_valid_types():
    for suite_type in ["scenario", "case", "mixed"]:
        suite = SuiteCreate(name="suite", type=suite_type)
        assert suite.type == suite_type


def test_suite_create_validates_ids_max_count():
    with pytest.raises(ValidationError, match="最多包含 100"):
        SuiteCreate(name="suite", type="case", case_ids=list(range(101)))

    with pytest.raises(ValidationError, match="最多包含 100"):
        SuiteCreate(name="suite", type="scenario", scenario_ids=list(range(101)))


def test_suite_create_validates_tags_max_count():
    with pytest.raises(ValidationError, match="最多包含 20"):
        SuiteCreate(name="suite", type="case", tags=[f"tag{i}" for i in range(21)])


def test_suite_create_validates_tags_not_empty():
    with pytest.raises(ValidationError, match="标签不能为空"):
        SuiteCreate(name="suite", type="case", tags=["tag1", "  ", "tag3"])


def test_suite_create_trims_name():
    suite = SuiteCreate(name="  suite  ", type="case")
    assert suite.name == "suite"


def test_suite_create_trims_description():
    suite = SuiteCreate(name="suite", description="  desc  ", type="case")
    assert suite.description == "desc"


def test_suite_create_nullifies_empty_description():
    suite = SuiteCreate(name="suite", description="   ", type="case")
    assert suite.description is None


def test_suite_create_accepts_all_optional_fields():
    suite = SuiteCreate(
        name="suite",
        description="desc",
        type="mixed",
        scenario_ids=[1, 2],
        case_ids=[10, 11],
        tags=["smoke", "p0"],
    )
    assert suite.name == "suite"
    assert suite.description == "desc"
    assert suite.type == "mixed"
    assert suite.scenario_ids == [1, 2]
    assert suite.case_ids == [10, 11]
    assert suite.tags == ["smoke", "p0"]


def test_suite_update_validates_name_whitespace():
    with pytest.raises(ValidationError, match="不能为空或纯空格"):
        SuiteUpdate(name="   ")


def test_suite_update_allows_partial_update():
    update = SuiteUpdate(name="new name")
    assert update.name == "new name"
    assert update.type is None
    assert update.description is None
