import pytest

from core.exceptions import NotFoundError, ValidationError
from infrastructure.strategies.filesystem_strategy_params_repository import (
    FilesystemStrategyParamsRepository,
)

VALID_JSON = '{"conditions": [{"left": "adx", "op": ">=", "right": {"value": 25}}]}'


def make_repo(tmp_path):
    return FilesystemStrategyParamsRepository(tmp_path)


def test_get_params_returns_none_when_no_file_exists(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.get_params("no_such_strategy") is None


def test_create_then_get_round_trip(tmp_path):
    repo = make_repo(tmp_path)

    repo.create_params("my_strategy", VALID_JSON)

    assert repo.get_params("my_strategy") == VALID_JSON


def test_create_rejects_duplicate(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_params("my_strategy", VALID_JSON)

    with pytest.raises(ValidationError):
        repo.create_params("my_strategy", VALID_JSON)


def test_create_rejects_invalid_json(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(ValidationError):
        repo.create_params("my_strategy", "{not valid json")

    assert repo.get_params("my_strategy") is None


def test_create_rejects_json_not_matching_schema(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(ValidationError):
        repo.create_params("my_strategy", '{"conditions": [{"left": "adx", "op": "bogus_op"}]}')


def test_save_requires_existing_file(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(NotFoundError):
        repo.save_params("does_not_exist", VALID_JSON)


def test_save_overwrites_existing_file(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_params("my_strategy", VALID_JSON)
    updated = '{"conditions": [{"left": "adx", "op": ">=", "right": {"value": 30}}]}'

    repo.save_params("my_strategy", updated)

    assert repo.get_params("my_strategy") == updated


def test_save_rejects_invalid_json_without_corrupting_file(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_params("my_strategy", VALID_JSON)

    with pytest.raises(ValidationError):
        repo.save_params("my_strategy", "{not valid json")

    assert repo.get_params("my_strategy") == VALID_JSON


def test_create_rejects_invalid_name(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(ValidationError):
        repo.create_params("Not-A-Valid-Name", VALID_JSON)


def test_delete_params_removes_the_file(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_params("my_strategy", VALID_JSON)

    repo.delete_params("my_strategy")

    assert repo.get_params("my_strategy") is None


def test_delete_params_is_a_no_op_when_no_file_exists(tmp_path):
    repo = make_repo(tmp_path)

    repo.delete_params("never_had_one")  # must not raise
