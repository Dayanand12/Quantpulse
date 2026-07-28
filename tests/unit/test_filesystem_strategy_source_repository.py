import pytest

from core.exceptions import NotFoundError, ValidationError
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)

VALID_SOURCE = "x = 1\n"


def make_repo(tmp_path):
    return FilesystemStrategySourceRepository(tmp_path)


def test_list_files_excludes_init_and_non_python(tmp_path):
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "orb_reversal.py").write_text(VALID_SOURCE, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    repo = make_repo(tmp_path)

    assert repo.list_files() == ["orb_reversal"]


def test_create_then_get_round_trip(tmp_path):
    repo = make_repo(tmp_path)

    repo.create_source("my_strategy", VALID_SOURCE)

    assert repo.get_source("my_strategy") == VALID_SOURCE
    assert "my_strategy" in repo.list_files()


def test_create_rejects_duplicate_name(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_source("my_strategy", VALID_SOURCE)

    with pytest.raises(ValidationError):
        repo.create_source("my_strategy", VALID_SOURCE)


def test_create_rejects_invalid_name(tmp_path):
    repo = make_repo(tmp_path)

    for bad_name in ["My_Strategy", "1strategy", "../evil", "has space", "has-dash"]:
        with pytest.raises(ValidationError):
            repo.create_source(bad_name, VALID_SOURCE)


def test_create_rejects_syntactically_invalid_source(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(ValidationError):
        repo.create_source("broken", "def f(:\n")

    assert repo.list_files() == []


def test_save_requires_existing_file(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(NotFoundError):
        repo.save_source("does_not_exist", VALID_SOURCE)


def test_save_overwrites_existing_file(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_source("my_strategy", "x = 1\n")

    repo.save_source("my_strategy", "x = 2\n")

    assert repo.get_source("my_strategy") == "x = 2\n"


def test_save_rejects_syntactically_invalid_source_without_corrupting_file(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_source("my_strategy", "x = 1\n")

    with pytest.raises(ValidationError):
        repo.save_source("my_strategy", "def f(:\n")

    assert repo.get_source("my_strategy") == "x = 1\n"


def test_get_source_raises_not_found_for_unknown_file(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(NotFoundError):
        repo.get_source("does_not_exist")
