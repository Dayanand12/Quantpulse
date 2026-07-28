"""Port: read/write access to a strategy's actual Python source file.

Deliberately separate from IStrategyRegistry — that interface answers
"what strategies imported successfully"; this one answers "what strategy
files exist," which must work even for a file that currently fails to
import (so the Strategy Builder can open and fix it).
"""

from abc import ABC, abstractmethod
from typing import List


class IStrategySourceRepository(ABC):
    @abstractmethod
    def list_files(self) -> List[str]:
        """Return every strategy file's name (without the .py extension)."""

    @abstractmethod
    def get_source(self, name: str) -> str:
        """Return a strategy file's raw source. Raises NotFoundError if missing."""

    @abstractmethod
    def save_source(self, name: str, source: str) -> None:
        """Overwrite an existing strategy file. Raises NotFoundError if it
        doesn't exist, ValidationError if `source` doesn't compile."""

    @abstractmethod
    def create_source(self, name: str, source: str) -> None:
        """Create a new strategy file. Raises ValidationError if the name
        is invalid, already exists, or `source` doesn't compile."""
