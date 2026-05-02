"""Deliberate root convenience command for one-off EDGAR fetches.

This entry point exists outside the ``python -m sec_graph`` dispatch tree so
that operators can pull filings directly from EDGAR without bootstrapping the
full pipeline CLI. Per ``docs/spec.md`` (CLI dispatch contract): if a full
``python -m sec_graph fetch`` subcommand is ever added that supersedes this
script, this file is deleted rather than maintained as a duplicate command
surface.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sec_graph.fetch.edgar import main


if __name__ == "__main__":
    raise SystemExit(main())
