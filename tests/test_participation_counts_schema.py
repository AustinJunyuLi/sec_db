import pytest
from pydantic import ValidationError

from sec_graph.schema import ParticipationCount


def test_participation_count_is_closed_cohort_observation() -> None:
    count = ParticipationCount(
        participation_count_id="zep_count_1",
        run_id="run_1",
        deal_id="zep_deal_1",
        cycle_id="zep_cycle_1",
        event_id=None,
        process_stage="nda_signed",
        actor_class="financial",
        count_min=25,
        count_max=25,
        count_qualifier="exact",
        named_subset_actor_ids=["zep_actor_party_x"],
        anonymous_remainder_count=24,
        evidence_ids=["zep_evidence_1"],
    )

    assert count.anonymous_remainder_count == 24
    assert not hasattr(count, "actor_creation_" + "required")


@pytest.mark.parametrize(
    "field,value",
    [("process_stage", "un" + "known"), ("actor_class", "potential_buyer"), ("actor_class", "shareholder")],
)
def test_participation_count_rejects_fallback_or_role_values(field: str, value: str) -> None:
    payload = {
        "participation_count_id": "zep_count_1",
        "run_id": "run_1",
        "deal_id": "zep_deal_1",
        "cycle_id": "zep_cycle_1",
        "event_id": None,
        "process_stage": "nda_signed",
        "actor_class": "financial",
        "count_min": 25,
        "count_max": 25,
        "count_qualifier": "exact",
        "named_subset_actor_ids": [],
        "anonymous_remainder_count": 25,
        "evidence_ids": ["zep_evidence_1"],
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ParticipationCount(**payload)
