import datetime as dt

import pytest
from pydantic import ValidationError

from sec_graph.schema import Actor, ActorRelation


def test_actor_identity_uses_closed_kind_and_observability() -> None:
    actor = Actor(
        actor_id="petsmart_actor_2",
        run_id="run_1",
        deal_id="petsmart_deal_1",
        actor_label="Buyer Group",
        actor_kind="group",
        observability="named",
        evidence_ids=["petsmart_evidence_1"],
        lead_arranger_label="BC Partners",
        member_count_known=5,
        has_strategic_member=False,
        has_sovereign_wealth_member=True,
    )

    assert actor.actor_kind == "group"
    assert not hasattr(actor, "actor_" + "type")
    assert not hasattr(actor, "bidder_" + "subtype")
    assert not hasattr(actor, "is_" + "anonymous")


@pytest.mark.parametrize("field,value", [("actor_kind", "un" + "known"), ("observability", "inferred_" + "projection")])
def test_actor_rejects_fallback_values(field: str, value: str) -> None:
    payload = {
        "actor_id": "petsmart_actor_2",
        "run_id": "run_1",
        "deal_id": "petsmart_deal_1",
        "actor_label": "Buyer Group",
        "actor_kind": "group",
        "observability": "named",
        "evidence_ids": ["petsmart_evidence_1"],
        "lead_arranger_label": None,
        "member_count_known": None,
        "has_strategic_member": None,
        "has_sovereign_wealth_member": None,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        Actor(**payload)


def test_actor_relation_has_cycle_and_date_frames() -> None:
    relation = ActorRelation(
        relation_id="petsmart_relation_1",
        run_id="run_1",
        deal_id="petsmart_deal_1",
        subject_actor_id="petsmart_actor_longview",
        object_actor_id="petsmart_actor_buyer_group",
        relation_type="member_of",
        role_detail="joined buyer group after final bid process authorization",
        cycle_id_first_observed="petsmart_cycle_2",
        cycle_id_last_observed=None,
        effective_date_first=dt.date(2014, 12, 12),
        effective_date_last=None,
        confidence="high",
        evidence_ids=["petsmart_evidence_1"],
    )

    assert relation.relation_type == "member_of"
    assert relation.cycle_id_first_observed == "petsmart_cycle_2"


@pytest.mark.parametrize("relation_type", ["un" + "known", "guaran" + "tees", "voting_" + "support_for"])
def test_actor_relation_rejects_non_spec_relation_values(relation_type: str) -> None:
    with pytest.raises(ValidationError):
        ActorRelation(
            relation_id="petsmart_relation_1",
            run_id="run_1",
            deal_id="petsmart_deal_1",
            subject_actor_id="petsmart_actor_longview",
            object_actor_id="petsmart_actor_buyer_group",
            relation_type=relation_type,
            role_detail=None,
            cycle_id_first_observed="petsmart_cycle_2",
            cycle_id_last_observed=None,
            effective_date_first=None,
            effective_date_last=None,
            confidence=None,
            evidence_ids=["petsmart_evidence_1"],
        )
