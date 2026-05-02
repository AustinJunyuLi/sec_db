import pytest
from pydantic import ValidationError

from sec_graph.schema import Event, EventActorLink


def test_event_subtype_stores_event_verb() -> None:
    event = Event(
        event_id="stec_event_1",
        run_id="run_1",
        deal_id="stec_deal_1",
        cycle_id="stec_cycle_1",
        event_type="process",
        event_subtype="excluded_by_target",
        event_date=None,
        description="special committee did not invite asset-only parties to continue",
        bid_value=None,
        bid_value_lower=None,
        bid_value_upper=None,
        bid_value_unit=None,
        consideration_type=None,
        evidence_ids=["stec_evidence_1"],
    )

    assert event.event_subtype == "excluded_by_target"


@pytest.mark.parametrize("value", ["ot" + "her", "un" + "known", "withdrew"])
def test_event_subtype_rejects_fallback_or_role_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Event(
            event_id="stec_event_1",
            run_id="run_1",
            deal_id="stec_deal_1",
            cycle_id="stec_cycle_1",
            event_type="process",
            event_subtype=value,
            event_date=None,
            description="bad subtype",
            bid_value=None,
            bid_value_lower=None,
            bid_value_upper=None,
            bid_value_unit=None,
            consideration_type=None,
            evidence_ids=["stec_evidence_1"],
        )


def test_event_actor_link_role_is_not_event_verb() -> None:
    link = EventActorLink(
        link_id="petsmart_link_1",
        run_id="run_1",
        event_id="petsmart_event_1",
        actor_id="petsmart_actor_longview",
        role="rollover_holder",
        role_detail="Longview agreed to roll over shares",
        evidence_ids=["petsmart_evidence_1"],
    )

    assert link.role == "rollover_holder"
