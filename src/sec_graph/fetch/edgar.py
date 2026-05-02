"""Download SEC filings from EDGAR and convert them with sec2md."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SEEDS_PATH = REPO_ROOT / "seeds.csv"
FILINGS_DIR = REPO_ROOT / "data" / "filings"

USER_AGENT = "Austin Li <junyu.li.24@ucl.ac.uk>"
MIN_DELAY_SEC = 0.15
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2.0

PRIMARY_FORM_TYPES = {
    "DEFM14A",
    "PREM14A",
    "SC TO-T",
    "SC TO-T/A",
    "SC 14D9",
    "SC 14D9/A",
    "S-4",
    "S-4/A",
}
EXCLUDED_FORM_TYPES = {"425"}

TENDER_OFFER_FORMS = {"SC TO-T", "SC TO-T/A"}
OFFER_TO_PURCHASE_EXHIBIT_PATTERN = re.compile(
    r"^EX-99\.\(?A\)?\(?1\)?\(?A\)?",
    re.IGNORECASE,
)

_last_request = 0.0


@dataclass(frozen=True)
class Seed:
    slug: str
    target_name: str
    acquirer: str
    date_announced: str
    primary_url: str
    is_reference: bool


@dataclass(frozen=True)
class FilingDocument:
    name: str
    form_type: str
    size_bytes: int | None
    url: str


class ExcludedFormTypeError(Exception):
    """Raised when the EDGAR filing is a known non-substantive form."""

    def __init__(self, form_type: str):
        self.form_type = form_type
        super().__init__(form_type)


def load_seeds(path: Path = SEEDS_PATH) -> list[Seed]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            Seed(
                slug=row["deal_slug"],
                target_name=row["target_name"],
                acquirer=row["acquirer"],
                date_announced=row["date_announced"],
                primary_url=row["primary_url"],
                is_reference=row["is_reference"].strip().lower() == "true",
            )
            for row in reader
        ]


def parse_accession(seed_url: str) -> tuple[str, str]:
    """Extract ``(cik, accession_no_dashes)`` from common EDGAR URL forms."""
    clean = seed_url.split("#", 1)[0].split("?", 1)[0]
    match = re.search(r"/data/(\d+)/(?:\d{18}/)?([0-9\-]+)-index\.htm", clean)
    if match:
        return match.group(1), match.group(2).replace("-", "")
    match = re.search(r"/data/(\d+)/(\d{18})(?:[/?]|$)", clean)
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"cannot parse CIK/accession from {seed_url}")


def canonical_index_url(cik: str, accession_no_dashes: str) -> str:
    dashed = (
        f"{accession_no_dashes[:10]}-"
        f"{accession_no_dashes[10:12]}-"
        f"{accession_no_dashes[12:]}"
    )
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession_no_dashes}/{dashed}-index.htm"
    )


def _rate_limited_get(url: str, accept: str = "text/html,*/*") -> bytes:
    """GET with SEC-friendly User-Agent, throttling, and backoff."""
    global _last_request
    for attempt in range(MAX_RETRIES):
        elapsed = time.time() - _last_request
        if elapsed < MIN_DELAY_SEC:
            time.sleep(MIN_DELAY_SEC - elapsed)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Host": "www.sec.gov",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                _last_request = time.time()
                return response.read()
        except urllib.error.HTTPError as exc:
            _last_request = time.time()
            if exc.code in (429, 403) and attempt < MAX_RETRIES - 1:
                sleep = BACKOFF_BASE_SEC ** (attempt + 1)
                print(f"  [{exc.code}] back-off {sleep:.1f}s", file=sys.stderr)
                time.sleep(sleep)
                continue
            raise
    raise RuntimeError(f"unreachable retry state for {url}")


def _parse_index_table(index_url: str) -> list[tuple[str, str, str, str]]:
    html = _rate_limited_get(index_url).decode("utf-8", errors="replace")
    rows = re.findall(
        r'<a href="([^"]+\.(?:htm|html))"[^>]*>([^<]+)</a>\s*</td>\s*'
        r'<td[^>]*>([^<]*)</td>\s*'
        r'<td[^>]*>([^<]*)</td>',
        html,
        re.IGNORECASE,
    )
    if not rows:
        raise ValueError(f"No document rows found on {index_url}")
    return rows


def _row_to_doc(row: tuple[str, str, str, str]) -> FilingDocument:
    href, name, form_type, size_cell = row
    size_text = size_cell.strip()
    size_bytes = int(size_text) if size_text.isdigit() else None
    url = href if href.startswith("http") else f"https://www.sec.gov{href}"
    return FilingDocument(
        name=name.strip(),
        form_type=form_type.strip(),
        size_bytes=size_bytes,
        url=url,
    )


def resolve_substantive_document(seed_url: str) -> tuple[FilingDocument, str]:
    """Resolve an EDGAR seed URL to the document that carries the narrative."""
    cik, accession = parse_accession(seed_url)
    index_url = canonical_index_url(cik, accession)
    rows = _parse_index_table(index_url)

    primary: FilingDocument | None = None
    for row in rows:
        doc = _row_to_doc(row)
        if doc.form_type in PRIMARY_FORM_TYPES:
            primary = doc
            break

    if primary is None:
        for row in rows:
            doc = _row_to_doc(row)
            if not doc.form_type.upper().startswith("EX-"):
                primary = doc
                break
    if primary is None:
        raise ValueError(f"No primary document identifiable on {index_url}")
    if primary.form_type in EXCLUDED_FORM_TYPES:
        raise ExcludedFormTypeError(primary.form_type)
    if primary.form_type not in PRIMARY_FORM_TYPES:
        raise ValueError(
            f"Unknown substantive form type {primary.form_type!r} on {index_url}"
        )

    if primary.form_type in TENDER_OFFER_FORMS:
        for row in rows:
            doc = _row_to_doc(row)
            if OFFER_TO_PURCHASE_EXHIBIT_PATTERN.match(doc.form_type):
                return doc, index_url
        print(
            f"  WARNING: {primary.form_type} filing but no Offer to Purchase "
            "exhibit found; using cover form",
            file=sys.stderr,
        )
    return primary, index_url


def _import_sec2md():
    try:
        import sec2md  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("sec2md is required. Install with: pip install sec2md") from exc
    return sec2md


def _sec2md_version() -> str:
    return str(getattr(_import_sec2md(), "__version__", "unknown"))


def _parse_html_with_sec2md(html: str):
    return _import_sec2md().parse_filing(
        html,
        user_agent=USER_AGENT,
        include_elements=True,
    )


def _write_pages(deal_dir: Path, pages: list[Any]) -> list[dict[str, Any]]:
    payload = [
        {
            "number": page.number,
            "tokens": getattr(page, "tokens", None),
            "element_count": len(getattr(page, "elements", []) or []),
            "content": page.content,
        }
        for page in pages
    ]
    (deal_dir / "pages.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    markdown_parts: list[str] = []
    for page in pages:
        markdown_parts.append(f"\n<!-- PAGE {page.number} -->\n")
        markdown_parts.append(page.content)
    (deal_dir / "raw.md").write_text("".join(markdown_parts), encoding="utf-8")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_deal(seed: Seed, force: bool = False) -> dict[str, Any]:
    deal_dir = FILINGS_DIR / seed.slug
    manifest_path = deal_dir / "manifest.json"
    if manifest_path.exists() and not force:
        print(f"[{seed.slug}] already fetched; skip (use --force to overwrite)")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    deal_dir.mkdir(parents=True, exist_ok=True)
    cik, accession = parse_accession(seed.primary_url)

    print(f"[{seed.slug}] resolving substantive document ...")
    doc, resolved_index_url = resolve_substantive_document(seed.primary_url)
    print(f"[{seed.slug}]   picked: {doc.form_type} {doc.name} ({doc.size_bytes} B)")

    print(f"[{seed.slug}] downloading {doc.url}")
    html_bytes = _rate_limited_get(doc.url)
    (deal_dir / "raw.htm").write_bytes(html_bytes)

    print(f"[{seed.slug}] converting with sec2md ...")
    pages = list(_parse_html_with_sec2md(html_bytes.decode("utf-8", errors="replace")))
    _write_pages(deal_dir, pages)

    manifest = {
        "slug": seed.slug,
        "target_name": seed.target_name,
        "acquirer": seed.acquirer,
        "date_announced": seed.date_announced,
        "is_reference": seed.is_reference,
        "source": {
            "seed_url": seed.primary_url,
            "index_url": resolved_index_url,
            "cik": cik,
            "accession": accession,
            "primary_document_url": doc.url,
            "primary_document_name": doc.name,
            "form_type": doc.form_type,
        },
        "artifacts": {
            "raw_htm_bytes": len(html_bytes),
            "raw_htm_sha256": hashlib.sha256(html_bytes).hexdigest(),
            "raw_md_bytes": (deal_dir / "raw.md").stat().st_size,
            "raw_md_sha256": _sha256_file(deal_dir / "raw.md"),
            "pages_json_sha256": _sha256_file(deal_dir / "pages.json"),
            "pages_count": len(pages),
        },
        "fetch": {
            "user_agent": USER_AGENT,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "sec2md_version": _sec2md_version(),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"[{seed.slug}] done: {len(pages)} pages, "
        f"{manifest['artifacts']['raw_md_bytes'] / 1024:.1f} KB markdown"
    )
    return manifest


def select_seeds(seeds: list[Seed], *, slug: str | None, reference_only: bool, all_deals: bool) -> list[Seed]:
    if slug:
        selected = [seed for seed in seeds if seed.slug == slug]
        if not selected:
            raise SystemExit(f"slug {slug} not in seeds.csv")
        return selected
    if reference_only:
        return [seed for seed in seeds if seed.is_reference]
    if all_deals:
        return seeds
    raise SystemExit("one of --slug, --reference-only, or --all is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="fetch one deal by slug")
    group.add_argument("--reference-only", action="store_true", help="fetch reference deals")
    group.add_argument("--all", action="store_true", help="fetch every deal in seeds.csv")
    parser.add_argument("--force", action="store_true", help="overwrite existing manifest artifacts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    targets = select_seeds(
        load_seeds(),
        slug=args.slug,
        reference_only=args.reference_only,
        all_deals=args.all,
    )
    print(f"fetching {len(targets)} deal(s) with User-Agent: {USER_AGENT}")
    ok = 0
    for seed in targets:
        try:
            process_deal(seed, force=args.force)
            ok += 1
        except ExcludedFormTypeError as exc:
            print(
                f"skipping slug={seed.slug}: form_type={exc.form_type} is excluded",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001 - keep batch fetches isolated.
            print(f"[{seed.slug}] FAILED: {exc}", file=sys.stderr)
    print(f"\n{ok}/{len(targets)} deals fetched successfully")
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
