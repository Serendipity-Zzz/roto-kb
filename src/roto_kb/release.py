from __future__ import annotations

from dataclasses import dataclass


class ReleaseConflict(RuntimeError): pass


@dataclass
class ReleaseRegistry:
    """Small deterministic release state machine used by local/fake deployments."""
    active: str = "rel_empty"
    previous: str | None = None

    def activate(self, release_id: str, *, ready: bool = True) -> str:
        if not ready: raise ReleaseConflict("only ready releases can be activated")
        if not release_id.startswith("rel_") or release_id == "rel_empty": raise ReleaseConflict("invalid release")
        self.previous, self.active = self.active, release_id
        return self.active

    def rollback(self, release_id: str | None = None) -> str:
        target = release_id or self.previous
        if not target or target == "rel_empty": raise ReleaseConflict("no recoverable previous release")
        return self.activate(target)
