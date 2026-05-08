"""Concrete tool handlers used by live agents.

Each function returns a JSON-serialisable dict and is registered as the
handler for the matching `ToolDefinition`. Handlers do not mutate state
— they call into `RetrievalIndex` / `retrieval.tools` only.
"""

from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from ..agents.roles import AgentRole
from ..llm.tool_loop import ToolDefinition
from ..retrieval.index import RetrievalIndex
from ..retrieval.tools import (
    normalize_actor_label,
    parse_count,
    parse_date,
    parse_money,
    verify_quote,
)
from .recorders import ToolCallRecorder


# ---------------------------------------------------------------- helpers

def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if hasattr(obj, "model_dump"):
        return _to_jsonable(obj.model_dump())
    return str(obj)


def _wrap(handler: Callable[[dict], Any], *, role: AgentRole, name: str, recorder: ToolCallRecorder) -> Callable[[dict], Any]:
    def wrapped(args: dict) -> Any:
        started = time.perf_counter()
        result = handler(args)
        elapsed = int((time.perf_counter() - started) * 1000)
        json_result = _to_jsonable(result)
        summary = (
            {"keys": sorted(json_result.keys())}
            if isinstance(json_result, dict)
            else {"type": type(json_result).__name__}
        )
        recorder.record(
            role=role.value,
            tool_name=name,
            arg_keys=sorted(args.keys()),
            result_summary=summary,
            latency_ms=elapsed,
        )
        return json_result
    return wrapped


# ---------------------------------------------------------------- tool defs

def _search_filing_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        query = str(args["query"])
        k = int(args.get("k", 5))
        hits = index.bm25(query, k=k)
        return {
            "hits": [
                {
                    "paragraph_id": h.paragraph_id,
                    "score": h.score,
                    "text": h.paragraph.text,
                }
                for h in hits
            ],
        }
    return ToolDefinition(
        name="search_filing",
        description="BM25-style search across filing paragraphs. Returns paragraph_id + verbatim text.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer"},
            },
            "required": ["query"],
        },
        handler=_wrap(handler, role=role, name="search_filing", recorder=recorder),
    )


def _get_paragraph_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        paragraph_id = str(args["paragraph_id"])
        try:
            p = index.get_paragraph(paragraph_id)
        except KeyError:
            return {"found": False, "paragraph_id": paragraph_id}
        return {
            "found": True,
            "paragraph_id": p.paragraph_id,
            "ordinal": p.ordinal,
            "text": p.text,
            "char_start": p.char_start,
            "char_end": p.char_end,
        }
    return ToolDefinition(
        name="get_paragraph",
        description="Fetch a paragraph by id with verbatim text and offsets.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"paragraph_id": {"type": "string"}},
            "required": ["paragraph_id"],
        },
        handler=_wrap(handler, role=role, name="get_paragraph", recorder=recorder),
    )


def _get_neighborhood_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        pid = str(args["paragraph_id"])
        before = int(args.get("before", 1))
        after = int(args.get("after", 1))
        try:
            window = index.neighborhood(pid, before=before, after=after)
        except KeyError:
            return {"found": False, "paragraph_id": pid}
        return {
            "found": True,
            "paragraphs": [
                {"paragraph_id": p.paragraph_id, "text": p.text}
                for p in window
            ],
        }
    return ToolDefinition(
        name="get_neighborhood",
        description="Fetch paragraphs around a paragraph id. before/after are non-negative integers.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "paragraph_id": {"type": "string"},
                "before": {"type": "integer"},
                "after": {"type": "integer"},
            },
            "required": ["paragraph_id"],
        },
        handler=_wrap(handler, role=role, name="get_neighborhood", recorder=recorder),
    )


def _verify_quote_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        quote = str(args["quote"])
        v = verify_quote(index, quote)
        return {
            "verbatim_present": v.verbatim_present,
            "ambiguity": v.ambiguity,
            "paragraph_ids": list(v.paragraph_ids),
            "positions": [list(p) for p in v.positions],
        }
    return ToolDefinition(
        name="verify_quote",
        description="Confirm a quote is verbatim in the filing. Returns paragraph_ids + positions.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"quote": {"type": "string"}},
            "required": ["quote"],
        },
        handler=_wrap(handler, role=role, name="verify_quote", recorder=recorder),
    )


def _parse_date_def(*, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        d = parse_date(str(args["text"]))
        return _to_jsonable(d)
    return ToolDefinition(
        name="parse_date",
        description="Parse a date phrase. Vague forms (e.g. 'early March 2026') are flagged ambiguous.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_wrap(handler, role=role, name="parse_date", recorder=recorder),
    )


def _parse_money_def(*, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        m = parse_money(str(args["text"]))
        return _to_jsonable(m)
    return ToolDefinition(
        name="parse_money",
        description="Parse a money phrase. Preserves per_share vs absolute unit.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_wrap(handler, role=role, name="parse_money", recorder=recorder),
    )


def _parse_count_def(*, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        c = parse_count(str(args["text"]))
        return _to_jsonable(c)
    return ToolDefinition(
        name="parse_count",
        description="Parse a count phrase. Ranges return min/max; approximate flags ambiguous.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_wrap(handler, role=role, name="parse_count", recorder=recorder),
    )


def _get_section_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        sid = str(args["section_id"])
        try:
            s = index.get_section(sid)
        except KeyError:
            return {"found": False, "section_id": sid}
        return {
            "found": True,
            "section_id": s.section_id,
            "label": s.label,
            "is_ambiguous_label": s.is_ambiguous_label,
            "char_start": s.char_start,
            "char_end": s.char_end,
            "body_paragraph_ids": list(s.body_paragraph_ids),
        }
    return ToolDefinition(
        name="get_section",
        description="Fetch a section record by id (label, range, body paragraph ids).",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"section_id": {"type": "string"}},
            "required": ["section_id"],
        },
        handler=_wrap(handler, role=role, name="get_section", recorder=recorder),
    )


def _get_table_def(index: RetrievalIndex, *, role: AgentRole, recorder: ToolCallRecorder) -> ToolDefinition:
    def handler(args: dict) -> Any:
        tid = str(args["table_id"])
        try:
            t = index.get_table(tid)
        except KeyError:
            return {"found": False, "table_id": tid}
        return {
            "found": True,
            "table_id": t.table_id,
            "paragraph_id": t.paragraph_id,
            "char_start": t.char_start,
            "char_end": t.char_end,
            "column_count": t.column_count,
            "row_count": t.row_count,
        }
    return ToolDefinition(
        name="get_table",
        description="Fetch a table record by id (offsets, row/column counts).",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"table_id": {"type": "string"}},
            "required": ["table_id"],
        },
        handler=_wrap(handler, role=role, name="get_table", recorder=recorder),
    )


def _normalize_actor_label_def(*, role: AgentRole, recorder: ToolCallRecorder, filing_id: str) -> ToolDefinition:
    def handler(args: dict) -> Any:
        a = normalize_actor_label(label=str(args["label"]), filing_id=filing_id)
        return _to_jsonable(a)
    return ToolDefinition(
        name="normalize_actor_label",
        description="Filing-local actor label canonicalisation. No cross-deal pooling.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
        handler=_wrap(handler, role=role, name="normalize_actor_label", recorder=recorder),
    )


_HANDLER_BUILDERS: dict[str, Callable[..., ToolDefinition]] = {
    "search_filing": _search_filing_def,
    "get_section": _get_section_def,
    "get_paragraph": _get_paragraph_def,
    "get_neighborhood": _get_neighborhood_def,
    "get_table": _get_table_def,
    "verify_quote": _verify_quote_def,
    "parse_date": lambda index, *, role, recorder: _parse_date_def(role=role, recorder=recorder),
    "parse_money": lambda index, *, role, recorder: _parse_money_def(role=role, recorder=recorder),
    "parse_count": lambda index, *, role, recorder: _parse_count_def(role=role, recorder=recorder),
    "normalize_actor_label": lambda index, *, role, recorder: _normalize_actor_label_def(
        role=role, recorder=recorder, filing_id=index.filing_id,
    ),
}


def build_tool_definitions(
    *,
    role: AgentRole,
    tool_names: list[str],
    index: RetrievalIndex,
    recorder: ToolCallRecorder,
) -> list[ToolDefinition]:
    """Build the concrete tools for a role from a name list."""
    out: list[ToolDefinition] = []
    for name in tool_names:
        if name not in _HANDLER_BUILDERS:
            # Unknown tool name — refuse to silently ignore.
            raise KeyError(f"no live handler builder for tool name {name!r}")
        out.append(_HANDLER_BUILDERS[name](index, role=role, recorder=recorder))
    return out
