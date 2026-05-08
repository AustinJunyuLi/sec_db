"""Deterministic canonical compiler.

The compiler is pure Python: given the deal-room store and a run id it
produces canonical rows with row-evidence links. Every canonical row id
is derived from the run id, deal slug, source ids, and payload keys, so
recompiling the same store on the same run id yields identical rows.

Per design spec §11.9 the compiler reads accepted attempts and evidence
bindings only; agents never own source coordinates and the compiler
never trusts payload-claimed offsets.
"""

from .compiler import (
    CanonicalCompiler,
    CompileRefusalReason,
    CompileResult,
    canonical_row_id,
)
from .models import (
    CanonicalActor,
    CanonicalDeal,
    CanonicalEvent,
    CanonicalEventActorLink,
    CanonicalFiling,
    CanonicalRowEvidenceLink,
    CanonicalSourceSpan,
)

__all__ = [
    "CanonicalActor",
    "CanonicalCompiler",
    "CanonicalDeal",
    "CanonicalEvent",
    "CanonicalEventActorLink",
    "CanonicalFiling",
    "CanonicalRowEvidenceLink",
    "CanonicalSourceSpan",
    "CompileRefusalReason",
    "CompileResult",
    "canonical_row_id",
]
