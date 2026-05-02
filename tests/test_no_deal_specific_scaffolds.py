"""Phase 6: production paths must not hardcode reference-deal scaffolding.

These tests are the binding contract for separating real general extraction
logic from temporary deal-specific (PetSmart, Longview, BC Partners, etc.)
scaffolding used during early bring-up. Production extractors must derive
labels from source patterns or filing metadata; production defaults must be
generic; the hand-authored PetSmart fixture remains only as a labeled schema
unit fixture, not as pipeline proof.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

import pytest

from sec_graph.cli import reconcile_cmd
from sec_graph.extract import pipeline as extract_pipeline
from sec_graph.extract import rules as rules_init
from sec_graph.extract.rules import actors as actors_module
from sec_graph.extract.rules import relations as relations_module
from sec_graph.reconcile import aliases as aliases_module
from sec_graph.reconcile import pipeline as reconcile_pipeline


_FORBIDDEN_NAMES = (
    "petsmart",
    "longview",
    "bc partners",
    "mac-gray",
    "providence",
    "saks",
    "zep",
    "imprivata",
    "medivation",
    "penford",
    "stec",
)


def _string_literals_outside_docstrings(source_text: str) -> list[tuple[int, str]]:
    """Return (lineno, value) for every str constant that is NOT a module/function/class docstring.

    Comments are stripped by the tokenizer pass we sidestep — `ast` already
    discards comments. Module/class/function docstring nodes (the FIRST
    `Expr(value=Constant(str))` inside their body) are skipped explicitly so
    "example: PetSmart" framing inside a docstring does not trip the test.
    """
    tree = ast.parse(source_text)
    docstring_nodes: set[int] = set()

    def _record_docstring(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    _record_docstring(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _record_docstring(node.body)

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_nodes:
                continue
            findings.append((node.lineno, node.value))
    return findings


def test_rule_extractors_do_not_hardcode_reference_deal_names() -> None:
    """`actors.py` and `relations.py` must not embed reference-deal name literals.

    AST walk: every non-docstring `str` constant is searched for forbidden
    reference-deal names. Comments are not searched (the AST drops them); only
    docstring positions are explicitly excluded so docstring framing like
    "example: PetSmart" stays allowed. Regex source strings, dict literals,
    and function-default values are all considered production code surfaces
    and are checked.
    """
    targets = (
        Path(actors_module.__file__),
        Path(relations_module.__file__),
    )
    violations: list[str] = []
    for path in targets:
        source = path.read_text(encoding="utf-8")
        for lineno, value in _string_literals_outside_docstrings(source):
            folded = value.casefold()
            for name in _FORBIDDEN_NAMES:
                if name in folded:
                    violations.append(f"{path.name}:{lineno}: contains '{name}' in literal {value!r}")
    assert not violations, "\n".join(violations)


def test_reconcile_aliases_do_not_fallback_to_slug_labels() -> None:
    """An unknown target slug must fail loudly, not silently echo the slug.

    The previous shape returned `slug` itself as the label for any unknown
    deal. That fabricates a target identity. Phase 6 contract: unknown labels
    raise, OR return a sentinel whose downstream use is rejected. Here we
    expect the raise path because no sentinel surface exists.
    """
    unknown_slug = "this-slug-does-not-exist-anywhere-in-seeds-or-manifest"
    with pytest.raises(Exception) as excinfo:
        aliases_module.target_label(unknown_slug)
    # The error must NAME the unresolved slug so reviewers can act on it.
    assert unknown_slug in str(excinfo.value), (
        f"target_label() must name the unresolved slug in its error; got {excinfo.value!r}"
    )


_HISTORICAL_RUN_IDS = (
    "extract-smoke",
    "reconcile-real",
    "track-b-petsmart",
    "reference-three",
)


def _function_default_strings(func) -> list[str]:
    sig = inspect.signature(func)
    return [
        param.default
        for param in sig.parameters.values()
        if isinstance(param.default, str)
    ]


def test_run_ids_are_explicit_not_historical_smoke_defaults() -> None:
    """Default `run_id` values must not encode historical bring-up scaffolding.

    The old code shipped `extract-smoke`, `reconcile-real`, and
    `track-b-petsmart` as production defaults. Phase 6 contract: defaults are
    explicitly generic — `None` to require a caller-supplied id, or a
    timestamp-pattern that is plainly not a historical proof name.
    """
    surfaces: dict[str, list[str]] = {
        "reconcile_pipeline.reconcile_all": _function_default_strings(reconcile_pipeline.reconcile_all),
        "extract_pipeline.run_extract": _function_default_strings(extract_pipeline.run_extract),
        "rules.run_rules": _function_default_strings(rules_init.run_rules),
    }
    cli_parser = reconcile_cmd.build_parser()
    for action in cli_parser._actions:
        if action.dest == "run_id" and isinstance(action.default, str):
            surfaces.setdefault("cli.reconcile_cmd.run_id", []).append(action.default)

    violations: list[str] = []
    for surface, defaults in surfaces.items():
        for default in defaults:
            for forbidden in _HISTORICAL_RUN_IDS:
                if forbidden in default:
                    violations.append(
                        f"{surface}: default {default!r} contains historical scaffold {forbidden!r}"
                    )
    assert not violations, "\n".join(violations)


def test_hand_authored_petsmart_fixture_is_not_pipeline_proof() -> None:
    """The hand-authored PetSmart fixture must self-document as a schema unit fixture.

    The fixture remains useful for round-tripping Pydantic models and for
    minimal contract assertions, but it MUST NOT be confused with pipeline
    proof produced by ingest -> extract -> reconcile. Its `_meta` block is
    the binding self-label.
    """
    fixture_path = Path("tests/fixtures/canonical/petsmart.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    meta = payload.get("_meta")
    assert isinstance(meta, dict), "petsmart.json must carry a top-level `_meta` block"
    assert meta.get("role") == "schema_unit_fixture", (
        f"_meta.role must be 'schema_unit_fixture'; got {meta.get('role')!r}"
    )
    assert meta.get("NOT_pipeline_proof") is True, (
        "_meta.NOT_pipeline_proof must be True so future readers cannot "
        "confuse the fixture with pipeline output"
    )

    bidder_rows_path = Path("tests/fixtures/canonical/petsmart_bidder_rows.jsonl")
    first_line = bidder_rows_path.read_text(encoding="utf-8").splitlines()[0]
    # The bidder-rows JSONL has its own `_meta` line as the FIRST record so
    # readers see the same self-label even when streaming line-by-line.
    bidder_meta = json.loads(first_line)
    assert bidder_meta.get("_meta") is not None, (
        "petsmart_bidder_rows.jsonl must lead with a `_meta` record"
    )
    assert bidder_meta["_meta"].get("role") == "schema_unit_fixture"
    assert bidder_meta["_meta"].get("NOT_pipeline_proof") is True
