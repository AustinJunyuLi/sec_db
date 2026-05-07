"""Parallel Linkflow region request tests.

These tests prove that the new ``extract_linkflow_windows`` event loop:

1. Inserts windows in their original sequence order even when provider
   responses arrive out of order.
2. Honors ``SEC_GRAPH_REGION_MAX_CONCURRENCY=1`` (serial provider calls).
3. Honors ``SEC_GRAPH_REGION_MAX_CONCURRENCY=2`` (two concurrent calls).
4. Imports zero claims when any window's retries are exhausted.
5. Performs DuckDB writes on the caller thread, after every provider call
   has completed.
6. Records every attempt in ``stage_artifacts.jsonl`` under
   ``artifact_kind='linkflow_attempt'`` so failed-validation proof counts
   only current-run ledgered artifacts (no stale globbed paths).
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm import linkflow as linkflow_module
from sec_graph.extract.llm.linkflow import (
    WindowBundle,
    extract_linkflow_windows,
    run_linkflow_requests,
)
from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
    BidClaimPayload,
    EventClaimPayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
    ParticipationCountClaimPayload,
    SemanticClaimsPayload,
)
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.schema import (
    CleanFiling,
    Paragraph,
    SourceSpan,
    connect,
    evidence_fingerprint,
    init_schema,
    make_id,
    quote_hash,
)


RUN_ID = "2026-05-07T010203Z_smoke-deal_deadbeef"


# -- Filing fixture ---------------------------------------------------------


def _insert_filing(conn, tmp_path: Path) -> Path:
    text = (
        "Background of the Merger\n\n"
        "On January 1, 2020, Party A submitted a final proposal of $10.00 per share. "
        "The Company contacted 10 financial buyers. "
        "Parent was an acquisition vehicle of Buyer Group. "
        "The parties executed the merger agreement on January 5, 2020.\n"
    )
    source_path = tmp_path / "smoke-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("smoke-deal", "filing", 1),
        deal_slug="smoke-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=make_id("smoke-deal", "para", 1),
        filing_id=filing.filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=quote_hash(text),
    )
    text_hash = quote_hash(text)
    span = SourceSpan(
        evidence_id=make_id("smoke-deal", "evidence", 1),
        filing_id=filing.filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing.filing_id, 0, len(text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return source_path


def _supported_payload(window: LLMWindowRequest) -> SemanticClaimsPayload:
    allowed = set(window.allowed_claim_types)
    return SemanticClaimsPayload(
        actor_claims=[
            ActorClaimPayload(
                coverage_obligation_id=_first_obligation_id(window, "actor"),
                claim_type="actor",
                actor_label="Party A",
                actor_kind="organization",
                observability="named",
                confidence="high",
                quote_text="Party A submitted a final proposal",
            )
        ]
        if "actor" in allowed
        else [],
        event_claims=[
            EventClaimPayload(
                coverage_obligation_id=_first_obligation_id(window, "event"),
                claim_type="event",
                event_type="transaction",
                event_subtype="merger_agreement_executed",
                event_date="2020-01-05",
                description="The parties executed the merger agreement.",
                actor_label="Party A",
                actor_role="bid_submitter",
                confidence="high",
                quote_text="executed the merger agreement on January 5, 2020",
            )
        ]
        if "event" in allowed
        else [],
        bid_claims=[
            BidClaimPayload(
                coverage_obligation_id=_first_obligation_id(window, "bid"),
                claim_type="bid",
                bidder_label="Party A",
                bid_date="2020-01-01",
                bid_value=10.0,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit="per_share",
                consideration_type="cash",
                bid_stage="final",
                confidence="high",
                quote_text="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
            )
        ]
        if "bid" in allowed
        else [],
        participation_count_claims=[
            ParticipationCountClaimPayload(
                coverage_obligation_id=_first_obligation_id(window, "participation_count"),
                claim_type="participation_count",
                process_stage="contacted",
                actor_class="financial",
                count_min=10,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="contacted 10 financial buyers",
            )
        ]
        if "participation_count" in allowed
        else [],
        actor_relation_claims=[
            ActorRelationClaimPayload(
                coverage_obligation_id=_first_obligation_id(window, "actor_relation"),
                claim_type="actor_relation",
                subject_label="Parent",
                object_label="Buyer Group",
                relation_type="acquisition_vehicle_of",
                role_detail="acquisition vehicle",
                effective_date_first=None,
                confidence="high",
                quote_text="Parent was an acquisition vehicle of Buyer Group",
            )
        ]
        if "actor_relation" in allowed
        else [],
    )


def _first_obligation_id(window: LLMWindowRequest, claim_type: str) -> str:
    for obligation in window.coverage_obligations:
        if obligation.expected_claim_type == claim_type:
            return obligation.obligation_id
    raise AssertionError(f"window has no {claim_type} obligation")


# -- Stub Linkflow client ---------------------------------------------------


class _StubStream:
    """Async context manager that mimics ``client.responses.stream(...)``."""

    def __init__(self, output_text: str, response: dict[str, Any]) -> None:
        self._output_text = output_text
        self._response = response

    async def __aenter__(self) -> "_StubStream":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def __aiter__(self):
        async def _iter():
            for chunk in self._chunks():
                yield {"type": "response.output_text.delta", "delta": chunk}

        return _iter()

    def _chunks(self) -> list[str]:
        # One chunk is enough; the production stream may emit many.
        return [self._output_text]

    async def get_final_response(self) -> dict[str, Any]:
        return self._response


class _StubResponses:
    def __init__(self, parent: "_StubAsyncOpenAI") -> None:
        self._parent = parent

    def stream(self, *, model: str, reasoning, input, text):  # noqa: A002 - mirrors openai signature
        request_id = self._parent._extract_request_id(input)
        return self._parent._build_stream_for(request_id)


class _StubAsyncOpenAI:
    """Records call timing and returns canned payloads keyed by request_id.

    Tests inject a per-request behavior dict so each window can be made to
    arrive in any order, raise an exception, or block until released.
    """

    def __init__(
        self,
        windows: list[LLMWindowRequest],
        behaviors: dict[str, dict[str, Any]],
    ) -> None:
        self._windows = {window.request_id: window for window in windows}
        self._behaviors = behaviors
        self._lock = asyncio.Lock()
        self.in_flight = 0
        self.peak_in_flight = 0
        self.start_log: list[tuple[str, float]] = []
        self.end_log: list[tuple[str, float]] = []
        self.responses = _StubResponses(self)
        self._loop_thread_id: int | None = None

    def _extract_request_id(self, messages: list[dict[str, str]]) -> str:
        for message in messages:
            if message.get("role") != "user":
                continue
            for window in self._windows.values():
                if f"region_id: {window.region_id}\n" in message.get("content", ""):
                    return window.request_id
        raise AssertionError("could not match request_id from prompt")

    def _build_stream_for(self, request_id: str) -> "_StubStreamWrapper":
        return _StubStreamWrapper(self, request_id)

    async def __aenter__(self) -> "_StubAsyncOpenAI":
        self._loop_thread_id = threading.get_ident()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def close(self) -> None:  # pragma: no cover - context manager handles close
        return None


class _StubStreamWrapper:
    """Indirection so we can mark in-flight increments at iteration start."""

    def __init__(self, parent: _StubAsyncOpenAI, request_id: str) -> None:
        self._parent = parent
        self._request_id = request_id

    async def __aenter__(self) -> "_StubStreamWrapper":
        loop = asyncio.get_event_loop()
        async with self._parent._lock:
            self._parent.in_flight += 1
            self._parent.peak_in_flight = max(self._parent.peak_in_flight, self._parent.in_flight)
            self._parent.start_log.append((self._request_id, loop.time()))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        loop = asyncio.get_event_loop()
        async with self._parent._lock:
            self._parent.in_flight -= 1
            self._parent.end_log.append((self._request_id, loop.time()))
        return None

    def __aiter__(self):
        async def _iter():
            behavior = self._parent._behaviors.get(self._request_id, {})
            delay = float(behavior.get("delay", 0.0))
            if delay > 0:
                await asyncio.sleep(delay)
            error = behavior.get("raise")
            if error is not None:
                raise error
            output_text = behavior["output_text"]
            yield {"type": "response.output_text.delta", "delta": output_text}

        return _iter()

    async def get_final_response(self) -> dict[str, Any]:
        behavior = self._parent._behaviors.get(self._request_id, {})
        return behavior.get("final_response", {"status": "completed", "output_text": behavior.get("output_text", ""), "usage": None})


def _payload_text(window: LLMWindowRequest) -> str:
    return json.dumps(_supported_payload(window).model_dump(mode="json"), sort_keys=True)


# -- Helpers to drive provider behaviors ------------------------------------


def _success_behaviors(windows: list[LLMWindowRequest], delays: dict[str, float] | None = None) -> dict[str, dict[str, Any]]:
    delays = delays or {}
    behaviors: dict[str, dict[str, Any]] = {}
    for window in windows:
        text = _payload_text(window)
        behaviors[window.request_id] = {
            "delay": delays.get(window.request_id, 0.0),
            "output_text": text,
            "final_response": {
                "status": "completed",
                "output_text": text,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
    return behaviors


def _two_window_corpus(tmp_path: Path) -> tuple[Any, list[LLMWindowRequest], LLMProviderConfig]:
    """Build a fresh DuckDB with two regions (and therefore two windows).

    The smoke-deal evidence map normally produces a single region. To exercise
    the fan-out, we duplicate the region row with a distinct ``region_id`` so
    ``build_llm_windows`` returns two ``LLMWindowRequest`` instances.
    """

    conn = connect(":memory:")
    init_schema(conn)
    _insert_filing(conn, tmp_path)
    build_evidence_map(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID)
    _duplicate_region(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID, slug="smoke-deal")
    windows = build_llm_windows(conn, filing_id="smoke-deal_filing_1")
    assert len(windows) == 2, f"fixture must produce two windows; got {len(windows)}"
    config = LLMProviderConfig(provider_name="linkflow")
    return conn, windows, config


def _duplicate_region(conn, *, filing_id: str, run_id: str, slug: str) -> None:
    """Copy the single region row into a second row with the same paragraphs."""

    base = conn.execute(
        """
        SELECT region_kind, priority, start_paragraph_id, end_paragraph_id,
               paragraph_ids_json, trigger_phrases_json, expected_claim_types_json
        FROM evidence_regions
        WHERE filing_id = ?
        """,
        [filing_id],
    ).fetchone()
    assert base is not None
    new_region_id = f"{slug}_region_2"
    conn.execute(
        "INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            new_region_id,
            run_id,
            filing_id,
            slug,
            base[0],
            base[1] + 1,
            base[2],
            base[3],
            base[4],
            base[5],
            base[6],
        ],
    )
    obligations = conn.execute(
        """
        SELECT expected_claim_type, obligation_label, importance
        FROM coverage_obligations
        WHERE filing_id = ?
        ORDER BY obligation_id
        """,
        [filing_id],
    ).fetchall()
    for sequence, (claim_type, label, importance) in enumerate(obligations, start=1):
        new_obligation_id = f"{slug}_obligation_aux_{sequence}"
        conn.execute(
            "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_obligation_id,
                run_id,
                new_region_id,
                filing_id,
                slug,
                claim_type,
                label,
                importance,
                True,
            ],
        )


# -- Tests ------------------------------------------------------------------


def test_out_of_order_responses_insert_in_original_window_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    _conn, windows, config = _two_window_corpus(tmp_path)

    # Window 1 is slow, window 2 is fast: window 2 finishes first.
    behaviors = _success_behaviors(
        windows,
        delays={windows[0].request_id: 0.05, windows[1].request_id: 0.0},
    )
    stub = _StubAsyncOpenAI(windows, behaviors)
    bundles = asyncio.run(
        extract_linkflow_windows(
            windows,
            config,
            RUN_ID,
            max_concurrency=2,
            client_factory=lambda: stub,
        )
    )

    assert [bundle.sequence for bundle in bundles] == [1, 2]
    assert [bundle.request_id for bundle in bundles] == [w.request_id for w in windows]
    finish_order = [request_id for request_id, _t in stub.end_log]
    assert finish_order[0] == windows[1].request_id, "fast window must finish first"
    assert finish_order[-1] == windows[0].request_id


def test_concurrency_one_serializes_provider_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    monkeypatch.setenv("SEC_GRAPH_REGION_MAX_CONCURRENCY", "1")
    _conn, windows, config = _two_window_corpus(tmp_path)
    behaviors = _success_behaviors(
        windows,
        delays={w.request_id: 0.05 for w in windows},
    )
    stub = _StubAsyncOpenAI(windows, behaviors)

    asyncio.run(
        extract_linkflow_windows(
            windows,
            config,
            RUN_ID,
            client_factory=lambda: stub,
        )
    )

    assert stub.peak_in_flight == 1


def test_concurrency_two_allows_two_concurrent_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    monkeypatch.setenv("SEC_GRAPH_REGION_MAX_CONCURRENCY", "2")
    _conn, windows, config = _two_window_corpus(tmp_path)
    behaviors = _success_behaviors(
        windows,
        delays={w.request_id: 0.05 for w in windows},
    )
    stub = _StubAsyncOpenAI(windows, behaviors)

    asyncio.run(
        extract_linkflow_windows(
            windows,
            config,
            RUN_ID,
            client_factory=lambda: stub,
        )
    )

    assert stub.peak_in_flight == 2


def test_failed_window_imports_zero_claims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    conn, windows, config = _two_window_corpus(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Both windows succeed at the provider level, but the second window
    # raises a non-retryable contract error so the whole filing attempt fails.
    from sec_graph.extract.llm.models import LinkflowProviderContractError

    behaviors = _success_behaviors(windows)
    behaviors[windows[1].request_id]["raise"] = LinkflowProviderContractError("fatal stub error")

    def _factory():
        return _StubAsyncOpenAI(windows, behaviors)

    with pytest.raises(LLMContractError):
        run_linkflow_requests(
            conn,
            filing_id="smoke-deal_filing_1",
            run_id=RUN_ID,
            run_dir=run_dir,
            config=config,
            client_factory=_factory,
        )

    claim_count = conn.execute("SELECT count(*) FROM claims").fetchone()[0]
    assert claim_count == 0, "no claims may be imported from a failed filing attempt"
    claim_evidence_count = conn.execute("SELECT count(*) FROM claim_evidence").fetchone()[0]
    assert claim_evidence_count == 0
    cost_count = conn.execute("SELECT count(*) FROM cost_runtime_records").fetchone()[0]
    assert cost_count == 0

    # Both windows recorded artifacts (one success, one failure).
    ledger_path = run_dir / "stage_artifacts.jsonl"
    assert ledger_path.exists()
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    linkflow_rows = [row for row in rows if row.get("artifact_kind") == "linkflow_attempt"]
    assert len(linkflow_rows) == 2
    success_rows = [row for row in linkflow_rows if "_success.json" in row["artifact_path"]]
    failure_rows = [row for row in linkflow_rows if "_failure.json" in row["artifact_path"]]
    assert len(success_rows) == 1
    assert len(failure_rows) == 1


def test_duckdb_writes_happen_on_caller_thread_after_provider_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    conn, windows, config = _two_window_corpus(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    main_thread_id = threading.get_ident()
    insert_thread_ids: list[int] = []
    insert_calls_during_provider: list[bool] = []

    real_insert_llm_response = linkflow_module.insert_llm_response

    def _wrapped_insert(connection, request, response, *, run_id):
        insert_thread_ids.append(threading.get_ident())
        # No provider call must still be in flight when this fires.
        insert_calls_during_provider.append(stub.in_flight > 0)
        return real_insert_llm_response(connection, request, response, run_id=run_id)

    behaviors = _success_behaviors(
        windows,
        delays={w.request_id: 0.02 for w in windows},
    )
    stub = _StubAsyncOpenAI(windows, behaviors)

    monkeypatch.setattr(linkflow_module, "insert_llm_response", _wrapped_insert)

    run_linkflow_requests(
        conn,
        filing_id="smoke-deal_filing_1",
        run_id=RUN_ID,
        run_dir=run_dir,
        config=config,
        max_concurrency=2,
        client_factory=lambda: stub,
    )

    assert insert_thread_ids == [main_thread_id, main_thread_id], "DuckDB inserts must run on the caller thread"
    assert all(in_flight is False for in_flight in insert_calls_during_provider), (
        "every DuckDB insert must happen after every provider call has finished"
    )
    # All provider calls completed and ended before any insert started.
    end_times = [end for _request_id, end in stub.end_log]
    assert len(end_times) == 2
    final_provider_end = max(end_times)
    # Inserts happen after the gather() returns so we cannot timestamp them
    # the same way; instead assert that the in_flight gauge dropped to zero
    # before each insert.
    assert all(value is False for value in insert_calls_during_provider)
    # And both provider calls indeed peaked at concurrency=2.
    assert stub.peak_in_flight == 2
    # Sanity: the last provider end timestamp is finite.
    assert final_provider_end > 0


def test_failed_validation_proof_counts_only_ledgered_current_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider artifacts must be counted from ``stage_artifacts.jsonl`` only.

    The legacy ``artifacts/linkflow/{run_id}/...`` glob no longer exists. A
    stale file dropped at ``artifacts/linkflow`` outside the run directory must
    never inflate the current-run count.
    """

    monkeypatch.setenv("LINKFLOW_API_KEY", "stub")
    conn, windows, config = _two_window_corpus(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Drop a stale legacy file that the old code would have globbed; it must be ignored.
    stale_root = tmp_path / "artifacts" / "linkflow" / RUN_ID
    stale_root.mkdir(parents=True)
    (stale_root / "old_request_old_failure.json").write_text("{\"ghost\": true}", encoding="utf-8")

    behaviors = _success_behaviors(windows)
    stub = _StubAsyncOpenAI(windows, behaviors)

    run_linkflow_requests(
        conn,
        filing_id="smoke-deal_filing_1",
        run_id=RUN_ID,
        run_dir=run_dir,
        config=config,
        client_factory=lambda: stub,
    )

    ledger_path = run_dir / "stage_artifacts.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    linkflow_rows = [row for row in rows if row.get("artifact_kind") == "linkflow_attempt"]
    # Exactly one success per window; no entries for the stale legacy file.
    assert len(linkflow_rows) == len(windows)
    artifact_paths = [Path(row["artifact_path"]) for row in linkflow_rows]
    for path in artifact_paths:
        assert path.parts[0] == "linkflow", path
        assert "_success.json" in path.name
    # No legacy globbed artifacts from outside the run directory should leak in.
    assert not any("artifacts/linkflow" in str(path) for path in artifact_paths)


def test_region_max_concurrency_must_be_positive_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_GRAPH_REGION_MAX_CONCURRENCY", "0")
    with pytest.raises(ValueError):
        # We do not need a real run; the resolver runs synchronously.
        from sec_graph.extract.llm.linkflow import _resolve_max_concurrency  # noqa: PLC0415

        _resolve_max_concurrency()


def test_region_max_concurrency_default_is_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_GRAPH_REGION_MAX_CONCURRENCY", raising=False)
    from sec_graph.extract.llm.linkflow import _resolve_max_concurrency  # noqa: PLC0415

    assert _resolve_max_concurrency() == 2


def test_window_bundle_succeeded_property() -> None:
    request = _stub_window_request()
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=SemanticClaimsPayload(),
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )
    success = WindowBundle(sequence=1, request_id=request.request_id, request=request, response=response)
    assert success.succeeded is True

    failed = WindowBundle(sequence=2, request_id=request.request_id, request=request, error_message="boom")
    assert failed.succeeded is False


def _stub_window_request() -> LLMWindowRequest:
    from sec_graph.extract.llm.models import WindowObligation, WindowParagraph
    from sec_graph.schema import versions

    return LLMWindowRequest(
        request_id="stub_request_1",
        deal_slug="stub",
        deal_id="stub",
        filing_id="stub_filing_1",
        region_id="stub_region_1",
        window_id="stub_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="stub_para_1",
                source_span_id="stub_span_1",
                char_start=0,
                char_end=10,
                paragraph_text="stub text.",
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="stub_obl_1",
                expected_claim_type="actor",
                obligation_label="Stub label",
                importance="required",
            )
        ],
        allowed_claim_types=["actor"],
        schema_version=versions.SCHEMA_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        request_mode="claim_only_p8_relation_v1",
    )
