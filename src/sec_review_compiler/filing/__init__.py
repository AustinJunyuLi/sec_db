"""Filing package, source spans, and atlas — the immutable evidence layer."""

from .atlas import (
    Atlas,
    AtlasWarning,
    ExhibitRecord,
    FilingRecord,
    SectionCandidate,
    SectionRecord,
    TableRecord,
    build_atlas,
)
from .package import (
    Exhibit,
    FilingPackage,
    Paragraph,
    build_filing_package,
)
from .spans import SourceSpan

__all__ = [
    "Atlas",
    "AtlasWarning",
    "Exhibit",
    "ExhibitRecord",
    "FilingPackage",
    "FilingRecord",
    "Paragraph",
    "SectionCandidate",
    "SectionRecord",
    "SourceSpan",
    "TableRecord",
    "build_atlas",
    "build_filing_package",
]
