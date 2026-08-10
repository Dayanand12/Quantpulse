"""Port: durable storage for batch jobs (core/domain/batch_job.py) — lets
a background-processed bulk parameter sweep survive a browser close, a
page reload, or checking back tomorrow.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.domain.batch_job import BatchJob


class IBatchJobRepository(ABC):
    @abstractmethod
    def create(self, job: BatchJob) -> BatchJob:
        """Inserts a new job (typically status="pending", scenarios already
        populated with their validated/invalid status) and returns it with
        its assigned id."""

    @abstractmethod
    def save(self, job: BatchJob) -> BatchJob:
        """Overwrites an existing job's mutable state (status, each
        scenario's status/result/error, finished_at) — the background
        runner calls this after every scenario so progress is always
        durable, never only in the runner's own memory."""

    @abstractmethod
    def get(self, job_id: int) -> Optional[BatchJob]:
        """One job's full current state, or None if it doesn't exist."""

    @abstractmethod
    def list_for_strategy(self, strategy_name: str, limit: int = 20) -> List[BatchJob]:
        """Most recent jobs for a strategy, newest first — lets the UI
        reconnect to "is anything still running, or what happened to the
        last one" without the caller having to remember a job id."""
