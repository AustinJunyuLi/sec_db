"""Phase 9 (US-010) — full agent role surface."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from sec_review_compiler.agents import (
    AgentRole,
    FORBIDDEN_TOOL_NAMES,
    OmissionInspectorOutput,
    ROLE_ORDER,
    ROLE_OUTPUT_MODEL,
    role_output_model,
    role_prompt,
    role_prompt_hash,
    tools_for_role,
)
from sec_review_compiler.llm import (
    role_response_format,
    role_schema,
)


REQUIRED_ROLE_NAMES = {
    "scout",
    "party_relation_extractor",
    "timeline_bid_extractor",
    "count_coverage_extractor",
    "omission_inspector",
    "verifier",
    "consistency_checker",
}


# ---------------------------------------------------------------- role surface

class TestRoleSurface:
    def test_required_roles_present(self) -> None:
        assert {r.value for r in AgentRole} == REQUIRED_ROLE_NAMES

    def test_role_order_covers_all(self) -> None:
        assert set(ROLE_ORDER) == set(AgentRole)


# ---------------------------------------------------------------- schema + prompt

class TestEveryRoleHasArtifacts:
    @pytest.mark.parametrize("role", list(AgentRole))
    def test_every_role_has_strict_schema(self, role: AgentRole) -> None:
        schema = role_schema(role)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert isinstance(schema.get("required"), list) and schema["required"]

    @pytest.mark.parametrize("role", list(AgentRole))
    def test_role_response_format_is_strict(self, role: AgentRole) -> None:
        rf = role_response_format(role)
        assert rf["type"] == "json_schema"
        assert rf["strict"] is True
        assert rf["schema"]["additionalProperties"] is False
        assert role.value in rf["name"]

    @pytest.mark.parametrize("role", list(AgentRole))
    def test_every_role_has_prompt_and_hash(self, role: AgentRole) -> None:
        prompt = role_prompt(role)
        assert prompt and isinstance(prompt, str)
        digest = role_prompt_hash(role)
        # SHA-256 hex is 64 chars.
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_prompt_hashes_are_distinct_per_role(self) -> None:
        digests = {r: role_prompt_hash(r) for r in AgentRole}
        assert len(set(digests.values())) == len(AgentRole)

    @pytest.mark.parametrize("role", list(AgentRole))
    def test_every_role_has_pydantic_output_model(self, role: AgentRole) -> None:
        model = role_output_model(role)
        assert issubclass(model, BaseModel)


# ---------------------------------------------------------------- forbidden tools

class TestNoForbiddenTools:
    def test_forbidden_set_includes_baseline_and_answer_key(self) -> None:
        assert "compare_to_baseline" in FORBIDDEN_TOOL_NAMES
        assert "lookup_answer_key" in FORBIDDEN_TOOL_NAMES

    @pytest.mark.parametrize("role", list(AgentRole))
    def test_role_does_not_expose_forbidden_tool(self, role: AgentRole) -> None:
        allowed = tools_for_role(role)
        forbidden_seen = allowed & FORBIDDEN_TOOL_NAMES
        assert not forbidden_seen, (
            f"role {role.value!r} exposes forbidden tools: {sorted(forbidden_seen)}"
        )


# ---------------------------------------------------------------- omission inspector

class TestOmissionInspectorEmitsCoverageOnly:
    def test_payload_must_have_coverage_checks_key(self) -> None:
        with pytest.raises(ValidationError):
            OmissionInspectorOutput.model_validate({"prose": "hello"})

    def test_extra_top_level_keys_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OmissionInspectorOutput.model_validate({
                "coverage_checks": [],
                "speculation": "we think bids are missing",
            })

    def test_nested_coverage_extra_keys_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OmissionInspectorOutput.model_validate({
                "coverage_checks": [{
                    "category": "bids",
                    "subcategory": None,
                    "check_state": "checked_absent",
                    "required": True,
                    "evidence_paragraph_id": None,
                    "free_form_note": "not allowed",
                }],
            })

    def test_check_state_enum_enforced(self) -> None:
        with pytest.raises(ValidationError):
            OmissionInspectorOutput.model_validate({
                "coverage_checks": [{
                    "category": "bids",
                    "subcategory": None,
                    "check_state": "not_a_real_state",
                    "required": True,
                    "evidence_paragraph_id": None,
                }],
            })

    def test_omission_schema_has_no_prose_field(self) -> None:
        schema = role_schema(AgentRole.OMISSION_INSPECTOR)
        item_props = schema["properties"]["coverage_checks"]["items"]["properties"]
        # The schema only carries structured fields; no notes/description.
        assert set(item_props.keys()) == {
            "category",
            "subcategory",
            "check_state",
            "required",
            "evidence_paragraph_id",
        }


# ---------------------------------------------------------------- agents stay isolated

class TestAgentsModuleIsolation:
    """Regression of the US-006 isolation contract under the new role surface."""

    @staticmethod
    def _walk() -> list[str]:
        import sec_review_compiler.agents as pkg

        names: list[str] = ["sec_review_compiler.agents"]
        for _f, name, _is in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            names.append(name)
        return names

    def test_no_duckdb_or_store_import(self) -> None:
        for name in self._walk():
            mod = importlib.import_module(name)
            for attr in list(getattr(mod, "__dict__", {}).keys()):
                obj = getattr(mod, attr, None)
                module_name = getattr(obj, "__module__", None)
                if not module_name:
                    continue
                assert not module_name.startswith("duckdb"), (
                    f"agents module {name!r} exposes duckdb symbol via {attr!r}"
                )
                assert not module_name.startswith("sec_review_compiler.store"), (
                    f"agents module {name!r} exposes store symbol via {attr!r}"
                )

    def test_source_files_do_not_mention_duckdb(self) -> None:
        agents_dir = Path(__file__).resolve().parent.parent / "src" / "sec_review_compiler" / "agents"
        for path in agents_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "import duckdb" not in text, f"{path} imports duckdb"
            assert "from duckdb" not in text, f"{path} imports from duckdb"
            assert "sec_review_compiler.store" not in text, (
                f"{path} references the deal-room store"
            )
