import json
import re
from dataclasses import dataclass

import pytest

from sec_graph.fetch import edgar


def test_parse_accession_accepts_compact_nested_and_direct_urls() -> None:
    cases = [
        (
            "https://www.sec.gov/Archives/edgar/data/1421182/0001140361-22-004143-index.htm",
            ("1421182", "000114036122004143"),
        ),
        (
            "https://www.sec.gov/Archives/edgar/data/1421182/000114036122004143/0001140361-22-004143-index.htm#toc",
            ("1421182", "000114036122004143"),
        ),
        (
            "https://www.sec.gov/Archives/edgar/data/1421182/000114036122004143/formdefm14a.htm?x=1",
            ("1421182", "000114036122004143"),
        ),
    ]

    for url, expected in cases:
        assert edgar.parse_accession(url) == expected


def test_resolve_substantive_document_picks_offer_to_purchase_for_tender_offer(monkeypatch) -> None:
    monkeypatch.setattr(
        edgar,
        "_parse_index_table",
        lambda _: [
            ("/Archives/edgar/data/1/000000000000000001/cover.htm", "cover.htm", "SC TO-T", "100"),
            (
                "/Archives/edgar/data/1/000000000000000001/offer.htm",
                "offer.htm",
                "EX-99.(A)(1)(A)",
                "200",
            ),
        ],
    )

    doc, index_url = edgar.resolve_substantive_document(
        "https://www.sec.gov/Archives/edgar/data/1/000000000000000001/0000000000-00-000001-index.htm"
    )

    assert doc.name == "offer.htm"
    assert doc.form_type == "EX-99.(A)(1)(A)"
    assert index_url.endswith("/000000000000000001/0000000000-00-000001-index.htm")


def test_resolve_substantive_document_rejects_excluded_forms(monkeypatch) -> None:
    monkeypatch.setattr(
        edgar,
        "_parse_index_table",
        lambda _: [
            ("/Archives/edgar/data/1/000000000000000001/doc.htm", "doc.htm", "425", "100"),
        ],
    )

    with pytest.raises(edgar.ExcludedFormTypeError) as excinfo:
        edgar.resolve_substantive_document(
            "https://www.sec.gov/Archives/edgar/data/1/000000000000000001/0000000000-00-000001-index.htm"
        )

    assert excinfo.value.form_type == "425"


@dataclass
class FakePage:
    number: int
    content: str
    tokens: int
    elements: list[str]


def test_process_deal_writes_raw_markdown_pages_and_manifest(tmp_path, monkeypatch) -> None:
    seed = edgar.Seed(
        slug="synthetic",
        target_name="Synthetic Co",
        acquirer="Buyer Inc.",
        date_announced="2020-01-02",
        primary_url="https://www.sec.gov/Archives/edgar/data/1/000000000000000001/0000000000-00-000001-index.htm",
        is_reference=False,
    )
    doc = edgar.FilingDocument(
        name="primary.htm",
        form_type="DEFM14A",
        size_bytes=123,
        url="https://www.sec.gov/Archives/edgar/data/1/000000000000000001/primary.htm",
    )

    monkeypatch.setattr(edgar, "FILINGS_DIR", tmp_path / "data" / "filings")
    monkeypatch.setattr(edgar, "resolve_substantive_document", lambda _: (doc, "https://index"))
    monkeypatch.setattr(edgar, "_rate_limited_get", lambda _: b"<html>body</html>")
    monkeypatch.setattr(
        edgar,
        "_parse_html_with_sec2md",
        lambda html: [
            FakePage(1, "First page", 2, ["a"]),
            FakePage(2, "Second page", 3, ["b", "c"]),
        ],
    )
    monkeypatch.setattr(edgar, "_sec2md_version", lambda: "test-sec2md")

    manifest = edgar.process_deal(seed, force=False)

    deal_dir = tmp_path / "data" / "filings" / "synthetic"
    assert (deal_dir / "raw.htm").read_bytes() == b"<html>body</html>"
    assert "<!-- PAGE 1 -->" in (deal_dir / "raw.md").read_text()
    assert "<!-- PAGE 2 -->" in (deal_dir / "raw.md").read_text()
    assert json.loads((deal_dir / "pages.json").read_text()) == [
        {"number": 1, "tokens": 2, "element_count": 1, "content": "First page"},
        {"number": 2, "tokens": 3, "element_count": 2, "content": "Second page"},
    ]
    assert manifest["slug"] == "synthetic"
    assert manifest["source"]["primary_document_url"] == doc.url
    assert manifest["fetch"]["sec2md_version"] == "test-sec2md"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["artifacts"]["raw_htm_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["artifacts"]["raw_md_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["artifacts"]["pages_json_sha256"])
