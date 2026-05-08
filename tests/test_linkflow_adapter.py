"""Phase 5 (US-006) — Linkflow adapter, strict schemas, agent isolation."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from sec_review_compiler.agents.outputs import (
    ClaimAttemptOutput,
    EvidenceCitation,
    ScoutMap,
    VerifierVerdict,
)
from sec_review_compiler.errors import (
    InvalidLinkflowConfigError,
    MissingLinkflowCredentialsError,
)
from sec_review_compiler.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    LinkflowClientConfig,
    SUPPORTED_REASONING_EFFORTS,
    build_responses_client,
    consistency_finding_schema,
    extractor_claim_schema,
    scout_region_map_schema,
    strict_response_format,
    verifier_verdict_schema,
)


# ---------------------------------------------------------------- config

class TestLinkflowClientConfig:
    def test_defaults_when_env_missing(self) -> None:
        cfg = LinkflowClientConfig.from_env(env={})
        assert cfg.base_url == DEFAULT_BASE_URL
        assert cfg.model == DEFAULT_MODEL
        assert cfg.reasoning_effort == DEFAULT_REASONING_EFFORT
        assert cfg.max_concurrency == DEFAULT_MAX_CONCURRENCY
        assert cfg.api_key_present is False

    def test_reads_env(self) -> None:
        cfg = LinkflowClientConfig.from_env(env={
            "LINKFLOW_API_KEY": "irrelevant-test-token",
            "LINKFLOW_BASE_URL": "https://example.invalid/v1",
            "LINKFLOW_MODEL": "gpt-5.5",
            "LINKFLOW_REASONING_EFFORT": "high",
            "LINKFLOW_MAX_CONCURRENCY": "8",
        })
        assert cfg.api_key_present is True
        assert cfg.base_url == "https://example.invalid/v1"
        assert cfg.model == "gpt-5.5"
        assert cfg.reasoning_effort == "high"
        assert cfg.max_concurrency == 8

    def test_unsupported_reasoning_effort_rejected(self) -> None:
        # The probe validated only low/medium/high; xhigh is not validated.
        with pytest.raises(InvalidLinkflowConfigError):
            LinkflowClientConfig.from_env(env={"LINKFLOW_REASONING_EFFORT": "xhigh"})

    def test_concurrency_out_of_range_rejected(self) -> None:
        with pytest.raises(InvalidLinkflowConfigError):
            LinkflowClientConfig.from_env(env={"LINKFLOW_MAX_CONCURRENCY": "0"})
        with pytest.raises(InvalidLinkflowConfigError):
            LinkflowClientConfig.from_env(env={"LINKFLOW_MAX_CONCURRENCY": "9"})

    def test_concurrency_non_integer_rejected(self) -> None:
        with pytest.raises(InvalidLinkflowConfigError):
            LinkflowClientConfig.from_env(env={"LINKFLOW_MAX_CONCURRENCY": "many"})

    def test_supported_set_is_probe_validated(self) -> None:
        assert SUPPORTED_REASONING_EFFORTS == frozenset({"low", "medium", "high"})


# ---------------------------------------------------------------- credentials

class TestPreNetworkCredentialGate:
    def test_require_credentials_raises_without_key(self) -> None:
        cfg = LinkflowClientConfig.from_env(env={})
        with pytest.raises(MissingLinkflowCredentialsError):
            cfg.require_credentials()

    def test_build_responses_client_refuses_without_key(self) -> None:
        cfg = LinkflowClientConfig.from_env(env={})
        # Even if openai is importable, the build must refuse first.
        with pytest.raises(MissingLinkflowCredentialsError):
            build_responses_client(cfg, env={})

    def test_require_credentials_passes_when_key_present(self) -> None:
        cfg = LinkflowClientConfig.from_env(env={"LINKFLOW_API_KEY": "tok"})
        cfg.require_credentials()  # does not raise


# ---------------------------------------------------------------- strict schemas

class TestStrictSchemas:
    def test_scout_schema_has_no_additional_properties(self) -> None:
        schema = scout_region_map_schema()
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["regions"]

    def test_claim_schema_required_keys(self) -> None:
        schema = extractor_claim_schema()
        assert set(schema["required"]) == {
            "claim_type", "claim_fingerprint", "payload_json", "evidence",
        }
        assert schema["additionalProperties"] is False

    def test_verifier_schema_proposed_correction_nullable(self) -> None:
        schema = verifier_verdict_schema()
        assert schema["properties"]["proposed_correction_json"]["type"] == ["string", "null"]
        assert "proposed_correction_json" in schema["required"]

    def test_consistency_schema_severity_enum(self) -> None:
        schema = consistency_finding_schema()
        assert schema["properties"]["severity"]["enum"] == ["info", "warning", "blocking"]

    def test_strict_response_format_wraps_schema(self) -> None:
        wrapped = strict_response_format("scout_map", scout_region_map_schema())
        assert wrapped["type"] == "json_schema"
        assert wrapped["name"] == "scout_map"
        assert wrapped["strict"] is True
        # Provider-strict transform should leave additionalProperties=False
        assert wrapped["schema"]["additionalProperties"] is False


# ---------------------------------------------------------------- pydantic mirrors

class TestPydanticAgreement:
    def test_scout_map_round_trip(self) -> None:
        m = ScoutMap.model_validate({
            "regions": [{
                "name": "Background",
                "paragraph_ids": ["p:1"],
                "search_keywords": ["NDA"],
                "confidence": "high",
            }],
        })
        assert m.regions[0].name == "Background"

    def test_claim_attempt_extra_fields_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClaimAttemptOutput.model_validate({
                "claim_type": "timeline_event",
                "claim_fingerprint": "fp:1",
                "payload_json": "{}",
                "evidence": [],
                "extra": "boom",
            })

    def test_verifier_verdict_correction_can_be_null(self) -> None:
        v = VerifierVerdict.model_validate({
            "verdict": "confirm",
            "reasoning_summary": "looks fine",
            "supporting_evidence": [{"paragraph_id": "p:1", "quote": "hi"}],
            "proposed_correction_json": None,
            "confidence": 0.9,
        })
        assert v.proposed_correction_json is None

    def test_evidence_citation_required_fields(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EvidenceCitation.model_validate({"paragraph_id": "p:1"})


# ---------------------------------------------------------------- agent isolation

class TestAgentsCannotWriteToDuckDB:
    """Structural assertion: nothing in `agents.*` imports duckdb or store.*."""

    @staticmethod
    def _walk_agent_modules() -> list[str]:
        import sec_review_compiler.agents as agents_pkg

        names: list[str] = []
        for _finder, name, _ispkg in pkgutil.walk_packages(
            agents_pkg.__path__, agents_pkg.__name__ + "."
        ):
            names.append(name)
        names.append("sec_review_compiler.agents")
        return names

    def test_no_duckdb_import_in_agents(self) -> None:
        for name in self._walk_agent_modules():
            mod = importlib.import_module(name)
            source_attrs = list(getattr(mod, "__dict__", {}).keys())
            for attr in source_attrs:
                obj = getattr(mod, attr, None)
                module_name = getattr(obj, "__module__", None)
                if module_name and module_name.startswith("duckdb"):
                    raise AssertionError(
                        f"agents module {name!r} exposes duckdb symbol via {attr!r}"
                    )

    def test_no_store_import_in_agents(self) -> None:
        for name in self._walk_agent_modules():
            mod = importlib.import_module(name)
            for attr in list(getattr(mod, "__dict__", {}).keys()):
                obj = getattr(mod, attr, None)
                module_name = getattr(obj, "__module__", None)
                if module_name and module_name.startswith(
                    "sec_review_compiler.store"
                ):
                    raise AssertionError(
                        f"agents module {name!r} exposes store symbol via {attr!r}"
                    )

    def test_source_files_do_not_mention_duckdb(self) -> None:
        # Belt-and-braces: the files themselves must not import duckdb.
        from pathlib import Path

        agents_dir = Path(__file__).resolve().parent.parent / "src" / "sec_review_compiler" / "agents"
        for path in agents_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "import duckdb" not in text, f"{path} imports duckdb"
            assert "from duckdb" not in text, f"{path} imports from duckdb"
            assert "sec_review_compiler.store" not in text, (
                f"{path} references the deal-room store"
            )
