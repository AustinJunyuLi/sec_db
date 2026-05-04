"""Source-text support classification for applicability and coverage proof."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class SupportState(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SupportDecision:
    obligation_kind: str
    state: SupportState
    reason_code: str
    basis: tuple[str, ...]


def classify_obligation_support(obligation_kind: str, text: str) -> SupportDecision:
    folded = _fold(text)
    negative = _first_match(folded, _NEGATIVE_PATTERNS.get(obligation_kind, ()))
    positive = _first_match(folded, _POSITIVE_PATTERNS.get(obligation_kind, ()))
    if positive is not None:
        return SupportDecision(
            obligation_kind,
            SupportState.POSITIVE,
            "positive_source_support",
            (positive[1],),
        )
    if negative is not None:
        return SupportDecision(obligation_kind, SupportState.NEGATIVE, negative[0], (negative[1],))
    topic = _first_match(folded, _TOPIC_PATTERNS.get(obligation_kind, ()))
    if topic is not None:
        return SupportDecision(
            obligation_kind,
            SupportState.AMBIGUOUS,
            "topic_only_or_ambiguous",
            (topic[1],),
        )
    return SupportDecision(obligation_kind, SupportState.ABSENT, "source_support_absent", ())


def is_substantive_sale_process_text(text: str) -> bool:
    folded = _fold(text)
    if len(folded.split()) < 4:
        return False
    if _looks_cross_reference_only(folded):
        return False
    return any(
        marker in folded
        for marker in (
            "board",
            "committee",
            "proposal",
            "offer",
            "buyer",
            "party",
            "negotiat",
            "merger agreement",
            "contacted",
            "indication of interest",
            "exclusiv",
        )
    )


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _first_match(text: str, patterns: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
    for reason_code, pattern in patterns:
        match = re.search(pattern, text)
        if match is not None:
            return reason_code, match.group(0)
    return None


def _looks_cross_reference_only(text: str) -> bool:
    cross_ref_markers = (
        "the information set forth in",
        "is incorporated herein by reference",
        "for more information on",
        "for a review of",
        "see section",
        "see the section",
        "set forth under",
    )
    return any(marker in text for marker in cross_ref_markers) and len(text.split()) < 90


_POSITIVE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "contacted_count": (
        ("positive_source_support", r"\bcontacted\s+(?:a\s+total\s+of\s+|approximately\s+|by\s+)?\d+"),
        ("positive_source_support", r"\b\d+\s+potential\s+(?:buyers|bidders|parties|acquirers|participants)\b"),
        ("positive_source_support", r"\b\d+\s+(?:financial|strategic)\s+(?:buyers|parties)\b"),
    ),
    "ioi_count": (
        ("positive_source_support", r"\bindications?\s+of\s+interest\b"),
        ("positive_source_support", r"\bpreliminary\s+(?:non-?binding\s+)?(?:proposals?|indications?)\b"),
        ("positive_source_support", r"\biois?\b"),
    ),
    "first_round_count": (
        ("positive_source_support", r"\bfirst[\s-]round\b"),
        ("positive_source_support", r"\bfirst\s+phase\b"),
    ),
    "final_round_count": (
        ("positive_source_support", r"\bfinal[\s-]round\b"),
        ("positive_source_support", r"\bfinal\s+(?:phase|bids?)\b"),
        ("positive_source_support", r"\bbest\s+and\s+final\b"),
    ),
    "final_round_bid_event": (
        ("positive_source_support", r"\bfinal[\s-]round\s+bid\b"),
        ("positive_source_support", r"\bfinal\s+(?:bid|proposal)\s+(?:was\s+)?(?:submitted|received)\b"),
        ("positive_source_support", r"\bbest\s+and\s+final\s+(?:offer|proposal|bid)\b"),
    ),
    "exclusivity_grant": (
        ("positive_source_support", r"\bgranted\s+exclusivity\b"),
        ("positive_source_support", r"\bwilling\s+to\s+offer\b[^.]{0,120}\bexclusivity\s+period\b"),
        ("positive_source_support", r"\bsigned\s+an\s+agreement\b[^.]{0,120}\bexclusivity\s+period\b"),
        ("positive_source_support", r"\bexecuted\s+(?:an\s+)?exclusivity\s+agreement\b"),
        ("positive_source_support", r"\bexclusivity\s+agreement\b[^.]{0,120}\bproviding\s+for\s+exclusive\s+negotiations\b"),
        ("positive_source_support", r"\bauthorized\b[^.]{0,120}\bexclusivity\s+agreement\b"),
        ("positive_source_support", r"\bexclusive\s+negotiations?\s+until\b"),
    ),
    "go_shop_period": (
        ("positive_source_support", r"\bgo-?shop\s+(?:period|process|provision)\b"),
        ("positive_source_support", r"\bgo-?shop\b"),
    ),
    "buyer_group_composition": (
        ("positive_source_support", r"\bbuyer\s+group\b"),
        ("positive_source_support", r"\bconsortium\b"),
        ("positive_source_support", r"\bacquisition\s+vehicle\s+of\b"),
        ("positive_source_support", r"\btogether\s+(?:we\s+)?refer\s+to\s+as\b"),
        ("positive_source_support", r"\btogether\s+with\b.{0,80}\b(?:buyer|parent|sponsor)\b"),
    ),
    "rollover_holder": (
        ("positive_source_support", r"\bagreed\s+to\s+(?:roll\s*-?\s*over|rollover|retain)\b"),
        ("positive_source_support", r"\bwould\s+be\s+willing\s+to\s+.+?\broll-?over\b"),
        ("positive_source_support", r"\bretain\s+(?:equity|a\s+stake)\b"),
        ("positive_source_support", r"\bcontribute\s+shares\b"),
    ),
    "voting_support": (
        ("positive_source_support", r"\bentered\s+into\s+(?:(?:a|the)\s+)?(?:voting\s+and\s+support|voting|support)\s+agreements?\b"),
        ("positive_source_support", r"\bexecuted\s+(?:their\s+respective\s+|(?:(?:a|the)\s+))?(?:voting\s+and\s+support|voting|support)\s+agreements?\b"),
        ("positive_source_support", r"\bagreed\s+to\s+vote\b"),
        ("positive_source_support", r"\bvoting\s+and\s+support\s+agreements?\s+(?:was\s+|were\s+)?(?:executed|entered)\b"),
    ),
    "special_committee": (
        ("positive_source_support", r"\bformed\s+(?:a\s+)?(?:special|transaction)\s+committee\b"),
        ("positive_source_support", r"\bestablished\s+(?:a\s+)?(?:special|transaction)\s+committee\b"),
        ("positive_source_support", r"\bappointed\b.{0,80}\b(?:special|transaction)\s+committee\b"),
        ("positive_source_support", r"\b(?:special|transaction)\s+committee\b.{0,80}\bappointed\b"),
    ),
    "recusal": (
        ("positive_source_support", r"\b(?:director|mr\.?|ms\.?|mrs\.?)\s+[a-z][a-z.'-]*\b[^.]{0,80}\b(?:elected|agreed|decided)\s+to\s+recuse\s+(?:himself|herself|themselves)\b"),
        ("positive_source_support", r"\b(?:director|mr\.?|ms\.?|mrs\.?)\s+[a-z][a-z.'-]*\b[^.]{0,80}\brecused\s+(?:himself|herself|themselves)\b"),
        ("positive_source_support", r"\brecused\s+(?:himself|herself|themselves)\b[^.]{0,120}\b(?:board|committee|meeting|process|evaluation|negotiation|transaction)\b"),
        ("positive_source_support", r"\bdid\s+not\s+participate\b.{0,120}\b(?:board|committee|meeting|process|evaluation|negotiation|transaction)\b"),
    ),
    "financing_committed": (
        ("positive_source_support", r"\b(?:debt|equity)\s+commitment\s+(?:letter|documents?)\b"),
        ("positive_source_support", r"\bfinancing\s+commitment\s+(?:letter|documents?)\b"),
        ("positive_source_support", r"\bcommitted\s+(?:debt|equity|financing)\b"),
        ("positive_source_support", r"\bcommitting\s+to\s+fund\b"),
        ("positive_source_support", r"\bobtained\b.{0,80}\bfinancing\s+commitments?\b"),
    ),
    "amendment": (
        ("positive_source_support", r"\bamendment\s+(?:to\s+)?the\s+merger\s+agreement\b"),
        ("positive_source_support", r"\bamended\s+(?:and\s+restated\s+)?merger\s+agreement\b"),
    ),
}

_NEGATIVE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "exclusivity_grant": (
        ("negative_or_requested_only", r"\b(?:requested|sought|asked)\b.{0,120}\bexclusiv"),
        ("negative_or_requested_only", r"\bconsider(?:ed)?\s+whether\s+to\s+enter\b.{0,120}\bexclusiv"),
        ("negative_or_requested_only", r"\b(?:declined|rejected|refused|would\s+not\s+grant|would\s+not\s+enter)\b.{0,120}\bexclusiv"),
        ("negative_or_requested_only", r"\bexclusiv.{0,120}\b(?:not\s+justified|declined|rejected|refused)\b"),
        ("negative_or_requested_only", r"\bdraft\s+exclusivity\s+agreement\b"),
    ),
    "rollover_holder": (
        ("negative_or_requested_only", r"\b(?:would\s+not|will\s+not|not)\s+roll-?over\b"),
        ("negative_or_requested_only", r"\bpossible\s+(?:equity\s+)?rollover\b"),
        ("negative_or_requested_only", r"\bpossibility\s+of\s+(?:an\s+)?(?:equity\s+)?rollover\b"),
    ),
    "voting_support": (
        ("topic_only_or_ambiguous", r"\b(?:draft|form|proposed\s+form)\b.{0,80}\bvoting\s+(?:and\s+support\s+)?agreement\b"),
        ("topic_only_or_ambiguous", r"\bvote\s+in\s+favor\b.{0,120}\b(?:board|directors|recommend)\b"),
    ),
    "special_committee": (
        ("negative_or_not_formed", r"\bnot\s+to\s+form\b.{0,80}\b(?:special|transaction)\s+committee\b"),
        ("negative_or_not_formed", r"\bdid\s+not\s+form\b.{0,80}\b(?:special|transaction)\s+committee\b"),
    ),
    "recusal": (
        ("unrelated_bidder_nonparticipation", r"\bcompany\s+[a-z]\b.{0,120}\bdid\s+not\s+participate\b"),
        ("unrelated_bidder_nonparticipation", r"\bbidder\b.{0,120}\bdid\s+not\s+participate\b"),
        ("conditional_or_disclaimed", r"\bif\b.{0,120}\b(?:recuse|recused|recusal)\b"),
        ("conditional_or_disclaimed", r"\bshould\b.{0,120}\b(?:recuse|recused|recusal)\b"),
        ("conditional_or_disclaimed", r"\bnot\s+interested\s+in\s+participating\b.{0,120}\bsale\s+process\b"),
    ),
    "financing_committed": (
        ("negative_or_requested_only", r"\bdid\s+not\s+include\b.{0,80}\bfirm\s+financing\s+commitment\b"),
        ("negative_or_requested_only", r"\bno\s+firm\s+financing\s+commitment\b"),
    ),
}

_TOPIC_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "contacted_count": (("topic_only_or_ambiguous", r"\bcontacted\b"),),
    "ioi_count": (("topic_only_or_ambiguous", r"\b(?:indication|proposal)\b"),),
    "first_round_count": (("topic_only_or_ambiguous", r"\bfirst\b"),),
    "final_round_count": (("topic_only_or_ambiguous", r"\bfinal\b"),),
    "final_round_bid_event": (("topic_only_or_ambiguous", r"\bfinal\b"),),
    "exclusivity_grant": (("topic_only_or_ambiguous", r"\bexclusiv"),),
    "go_shop_period": (("topic_only_or_ambiguous", r"\bgo-?shop\b"),),
    "buyer_group_composition": (("topic_only_or_ambiguous", r"\b(?:merger\s+sub|buyer|group|vehicle|consortium)\b"),),
    "rollover_holder": (("topic_only_or_ambiguous", r"\broll-?over\b"),),
    "voting_support": (("topic_only_or_ambiguous", r"\b(?:voting|support)\s+agreement\b"),),
    "special_committee": (("topic_only_or_ambiguous", r"\b(?:special|transaction)\s+committee\b"),),
    "recusal": (("topic_only_or_ambiguous", r"\b(?:recus|did\s+not\s+participate|abstain)\b"),),
    "financing_committed": (("topic_only_or_ambiguous", r"\bfinancing\b"),),
    "amendment": (("topic_only_or_ambiguous", r"\bamend"),),
}
