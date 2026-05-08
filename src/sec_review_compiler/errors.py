"""Typed errors for sec_review_compiler.

Each error class names a single failure semantics so callers can react to it
without parsing messages. New error classes are added only when a real call
site needs to distinguish a new failure mode.
"""


class CompilerError(Exception):
    """Base class for sec_review_compiler errors."""


class InvalidRunIdError(CompilerError):
    """Raised when a value cannot be a canonical run id or slug."""


class AtomicWriteError(CompilerError):
    """Raised when an atomic write cannot be completed safely."""


class FilingPackageError(CompilerError):
    """Base class for filing package construction failures."""


class MissingTenderOfferExhibitError(FilingPackageError):
    """Raised when a tender-offer filing lacks the substantive offer exhibit.

    Per the design spec §6, the substantive offer-to-purchase exhibit is
    required for tender-offer deal processing. The package builder must fail
    loudly rather than substitute a cover document.
    """
