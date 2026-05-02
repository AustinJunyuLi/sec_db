import pytest
from pydantic import ValidationError

from sec_graph.schema import Judgment, latest_judgments


def test_projection_eligibility_judgment_shape() -> None:
    judgment = Judgment(
        judgment_id="petsmart_judgment_1",
        run_id="run_1",
        judgment_kind="projection_eligibility",
        target_table=None,
        target_id=None,
        target_column=None,
        prior_value=None,
        new_value=None,
        projection_name="bidder_cycle_baseline_v1",
        actor_id="petsmart_actor_buyer_group",
        included=True,
        rule_id="bidder_cycle_baseline_v1.consortium_collapse",
        evidence_ids=["petsmart_evidence_1"],
        supersedes_judgment_id=None,
        created_at="2026-05-02T00:00:00+00:00",
        created_by="test",
    )

    assert judgment.judgment_kind == "projection_eligibility"
    assert not hasattr(judgment, "judgment_" + "type")
    assert not hasattr(judgment, "judgment_" + "value")


def test_judgment_rejects_legacy_type_value_shape() -> None:
    with pytest.raises(ValidationError):
        Judgment(
            judgment_id="bad_judgment_1",
            run_id="run_1",
            **{"judgment_" + "type": "formal_boundary"},
            **{"judgment_" + "value": "event_1"},
            confidence="high",
            evidence_ids=["evidence_1"],
        )


def test_latest_judgments_uses_supersession_chain() -> None:
    old = Judgment(
        judgment_id="judgment_1",
        run_id="run_1",
        judgment_kind="projection_eligibility",
        target_table=None,
        target_id=None,
        target_column=None,
        prior_value=None,
        new_value=None,
        projection_name="bidder_cycle_baseline_v1",
        actor_id="actor_1",
        included=False,
        rule_id="bidder_cycle_baseline_v1.admission",
        evidence_ids=["evidence_1"],
        supersedes_judgment_id=None,
        created_at="2026-05-02T00:00:00+00:00",
        created_by="test",
    )
    new = old.model_copy(update={"judgment_id": "judgment_2", "included": True, "supersedes_judgment_id": "judgment_1"})

    assert latest_judgments([old, new]) == [new]
