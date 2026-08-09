"""IStrategyParamsRepository implemented over the filesystem — mirrors
FilesystemStrategySourceRepository's safety conventions (name validation,
content validated before it ever touches disk) but for a strategy's
conditions.json instead of its .py source.
"""

import json
import re
from pathlib import Path
from typing import Optional

from core.application.interfaces.strategy_params_repository import IStrategyParamsRepository
from core.domain.strategy_conditions import validate_conditions_json
from core.exceptions import NotFoundError, ValidationError

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class FilesystemStrategyParamsRepository(IStrategyParamsRepository):
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path_for(self, name: str) -> Path:
        if not _NAME_PATTERN.match(name):
            raise ValidationError(
                "Strategy name must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores."
            )
        return self._directory / f"{name}.json"

    def _validate(self, raw_json: str) -> None:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
        try:
            validate_conditions_json(data)
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            raise ValidationError(f"Doesn't match the strategy-conditions schema: {e}")

    def get_params(self, name: str) -> Optional[str]:
        path = self._path_for(name)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def save_params(self, name: str, raw_json: str) -> None:
        path = self._path_for(name)
        if not path.exists():
            raise NotFoundError(f"Strategy has no params file yet: {name}")
        self._validate(raw_json)
        path.write_text(raw_json, encoding="utf-8")

    def create_params(self, name: str, raw_json: str) -> None:
        path = self._path_for(name)
        if path.exists():
            raise ValidationError(f"Strategy params file already exists: {name}")
        self._validate(raw_json)
        path.write_text(raw_json, encoding="utf-8")

    def delete_params(self, name: str) -> None:
        path = self._path_for(name)
        if path.exists():
            path.unlink()
