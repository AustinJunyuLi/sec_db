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


class LinkflowError(CompilerError):
    """Base class for Linkflow adapter errors."""


class MissingLinkflowCredentialsError(LinkflowError):
    """Raised before any network call when LINKFLOW_API_KEY is missing."""


class InvalidLinkflowConfigError(LinkflowError):
    """Raised when an environment-configured Linkflow value fails validation."""


class MalformedToolArgumentsError(LinkflowError):
    """Raised when an agent emits tool-call arguments that cannot be parsed.

    No silent recovery; the orchestrator surfaces this and the attempt is
    marked malformed in the audit log.
    """


class ToolDispatchError(LinkflowError):
    """Raised when an agent calls a tool not registered with the loop."""
