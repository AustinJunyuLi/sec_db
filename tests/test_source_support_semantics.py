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


# --------------------------------------------------------------------------- #
# Buyer-group / member_of quote support tests (Task 5)                        #
# --------------------------------------------------------------------------- #

from sec_graph.extract.source_support import (
    is_proposal_like_label,
    member_of_object_is_actor_like,
    member_of_quote_supports_pair,
    relation_quote_names_subject,
)


@pytest.mark.parametrize(
    "label",
    [
        "joint acquisition proposal",
        "consortium proposal",
        "the transaction",
        "Best and Final Offer",
        "first round bid",
        "the sale process",
    ],
)
def test_proposal_like_labels_are_rejected(label: str) -> None:
    assert is_proposal_like_label(label)
    assert not member_of_object_is_actor_like(label)


@pytest.mark.parametrize(
    "label",
    [
        "Buyer Group",
        "CSC/Pamplona",
        "Sponsor A",
        "Bay Capital Partners",
        "Acme Holdings, L.P.",
    ],
)
def test_actor_like_labels_are_accepted(label: str) -> None:
    assert not is_proposal_like_label(label)
    assert member_of_object_is_actor_like(label)


def test_member_of_object_rejects_empty_label() -> None:
    assert not member_of_object_is_actor_like("")
    assert not member_of_object_is_actor_like("   ")


def test_relation_quote_names_subject_accepts_literal_match() -> None:
    assert relation_quote_names_subject(
        "Sponsor A",
        "Sponsor A is a member of the Buyer Group.",
    )
    assert relation_quote_names_subject(
        "sponsor a",
        "Sponsor A is a member of the Buyer Group.",
    )


def test_relation_quote_names_subject_rejects_missing_subject() -> None:
    assert not relation_quote_names_subject(
        "Sponsor A",
        "Parent was an acquisition vehicle of Buyer Group.",
    )
    assert not relation_quote_names_subject("", "anything")
    assert not relation_quote_names_subject("Sponsor A", "")


def test_member_of_quote_supports_pair_requires_both_actors_named() -> None:
    quote = "Sponsor A and Sponsor B are members of the Buyer Group."
    assert member_of_quote_supports_pair("Sponsor A", "Buyer Group", quote)
    assert member_of_quote_supports_pair("Sponsor B", "Buyer Group", quote)


def test_member_of_quote_rejects_proposal_like_object() -> None:
    quote = "Sponsor A submitted a joint acquisition proposal with Sponsor B."
    assert not member_of_quote_supports_pair(
        "Sponsor A",
        "joint acquisition proposal",
        quote,
    )


def test_member_of_quote_rejects_quote_missing_subject() -> None:
    quote = "Sponsor B is a member of the Buyer Group."
    assert not member_of_quote_supports_pair("Sponsor A", "Buyer Group", quote)


def test_member_of_quote_rejects_quote_missing_object() -> None:
    quote = "Sponsor A signed a non-disclosure agreement."
    assert not member_of_quote_supports_pair("Sponsor A", "Buyer Group", quote)
