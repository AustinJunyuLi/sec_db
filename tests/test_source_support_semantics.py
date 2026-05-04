import pytest

from sec_graph.extract.source_support import SupportState, classify_obligation_support


@pytest.mark.parametrize(
    ("kind", "text", "basis"),
    [
        ("exclusivity_grant", "The board granted exclusivity to Buyer A.", "granted exclusivity"),
        (
            "special_committee",
            "The board formed a special committee of independent directors.",
            "formed a special committee",
        ),
        ("recusal", "Director C recused himself from the board's evaluation.", "recused himself"),
    ],
)
def test_positive_support(kind: str, text: str, basis: str) -> None:
    decision = classify_obligation_support(kind, text)
    assert decision.state == SupportState.POSITIVE
    assert basis.casefold() in " ".join(decision.basis).casefold()


@pytest.mark.parametrize(
    ("kind", "text", "reason"),
    [
        (
            "exclusivity_grant",
            "Buyer A requested exclusivity, and the board declined exclusivity.",
            "negative_or_requested_only",
        ),
        (
            "exclusivity_grant",
            "The board concluded that exclusivity was not justified.",
            "negative_or_requested_only",
        ),
        (
            "special_committee",
            "The board determined not to form a transaction committee.",
            "negative_or_not_formed",
        ),
        (
            "recusal",
            "Company F did not participate in a buyer offer.",
            "unrelated_bidder_nonparticipation",
        ),
    ],
)
def test_negative_or_unrelated_support(kind: str, text: str, reason: str) -> None:
    decision = classify_obligation_support(kind, text)
    assert decision.state == SupportState.NEGATIVE
    assert decision.reason_code == reason
