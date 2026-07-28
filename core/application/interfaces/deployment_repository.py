"""Port: persisted strategy deployments.

Restart-to-apply, same as the watchlist/strategy-config repositories it
supersedes — saving a new/edited deployment here doesn't affect a running
process until the next restart builds fresh DeploymentRuntimes from
whatever's enabled (see core/container.py).
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.domain.models import Deployment


class IDeploymentRepository(ABC):
    @abstractmethod
    def list_deployments(self) -> List[Deployment]:
        """Return every saved deployment (enabled or not)."""

    @abstractmethod
    def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """Look up a single deployment by id."""

    @abstractmethod
    def save_deployment(self, deployment: Deployment) -> None:
        """Create or update a deployment (upsert by id)."""

    @abstractmethod
    def delete_deployment(self, deployment_id: str) -> None:
        """Remove a deployment. No-op if it doesn't exist."""
