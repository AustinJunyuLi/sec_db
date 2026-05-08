"""Run manifest: the immutable record of a run's identity and config."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..config import LINKFLOW_PROBE_RUN_ID, config_hash
from .ids import RunId
from .io import atomic_write_json

MANIFEST_FILENAME = "run_manifest.json"


class RunManifest(BaseModel):
    """Pinned identity of a compiler run; written once, never mutated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: datetime
    config_hash: str
    linkflow_probe_run_id: str = Field(default=LINKFLOW_PROBE_RUN_ID)
    package_version: str = Field(default=__version__)

    @classmethod
    def for_run(cls, run_id: RunId, config: dict[str, Any]) -> "RunManifest":
        return cls(
            run_id=str(run_id),
            started_at=run_id.started_at,
            config_hash=config_hash(config),
            linkflow_probe_run_id=LINKFLOW_PROBE_RUN_ID,
            package_version=__version__,
        )

    def write(self, run_dir: Path) -> Path:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / MANIFEST_FILENAME
        atomic_write_json(target, self.model_dump(mode="json"))
        return target
