"""IStrategySourceRepository implemented over the filesystem.

Reads/writes .py files directly in a given directory (the real strategies/
folder in production, a tmp_path in tests — see core/container.py for how
the real directory is resolved). Every write path validates the name
(blocks path traversal, keeps it a valid Python module name) and compiles
the source (never exec's it) before touching disk, so a bad edit produces
a clear 400 instead of a broken file that only fails at next restart.
"""

import re
from pathlib import Path
from typing import List

from core.application.interfaces.strategy_source_repository import IStrategySourceRepository
from core.exceptions import NotFoundError, ValidationError

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class FilesystemStrategySourceRepository(IStrategySourceRepository):
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path_for(self, name: str) -> Path:
        if not _NAME_PATTERN.match(name):
            raise ValidationError(
                "Strategy name must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores."
            )
        return self._directory / f"{name}.py"

    def _validate_syntax(self, source: str, name: str) -> None:
        try:
            compile(source, f"{name}.py", "exec")
        except SyntaxError as e:
            raise ValidationError(f"Syntax error: {e}")

    def list_files(self) -> List[str]:
        return sorted(p.stem for p in self._directory.glob("*.py") if p.stem != "__init__")

    def get_source(self, name: str) -> str:
        path = self._path_for(name)
        if not path.exists():
            raise NotFoundError(f"Strategy file not found: {name}")
        return path.read_text(encoding="utf-8")

    def save_source(self, name: str, source: str) -> None:
        path = self._path_for(name)
        if not path.exists():
            raise NotFoundError(f"Strategy file not found: {name}")
        self._validate_syntax(source, name)
        path.write_text(source, encoding="utf-8")

    def create_source(self, name: str, source: str) -> None:
        path = self._path_for(name)
        if path.exists():
            raise ValidationError(f"Strategy file already exists: {name}")
        self._validate_syntax(source, name)
        path.write_text(source, encoding="utf-8")
