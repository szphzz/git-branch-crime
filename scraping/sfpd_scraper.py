"""
SFPD CompStat crime-report scraper.

Steps:
  Scrape the Crime Reports page for monthly CompStat PDF links,
               then download each PDF.
  Read each PDF page with pdfplumber, detect which district the
               page belongs to, and parse the table rows into tidy records.
  Write CSV/JSON locally and upload JSON to the
               team's GCS bucket.

The Crime Reports page is static Drupal HTML, so requests + BeautifulSoup is
enough. The actual numbers live inside the PDFs.

Usage:
    python -m scraping.sfpd_scraper --since 2023-01          # backfill
    python -m scraping.sfpd_scraper --latest                 # newest month only
    python -m scraping.sfpd_scraper --since 2025-01 --upload # also push to GCS
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("sfpd_scraper")

BASE_URL = "https://www.sanfranciscopolice.org"
REPORTS_URL = f"{BASE_URL}/stay-safe/crime-data/crime-reports"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (USF DSAI692 student project; git-branch-crime) "
        "python-requests"
    )
}
DATA_DIR = Path(os.getenv("CRIME_DATA_DIR", Path(__file__).parent / "data"))

MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}

DISTRICTS = [
    "CITYWIDE", "CENTRAL", "SOUTHERN", "BAYVIEW", "MISSION", "NORTHERN",
    "PARK", "RICHMOND", "INGLESIDE", "TARAVAL", "TENDERLOIN",
]

# (regex for the row label at the start of a line, canonical category, section)
# Order matters: more specific labels first. Labels cover both the 2023-era
# layout (ALL CAPS) and the 2025+ Power BI layout (Title Case).
ROW_PATTERNS: list[tuple[str, str, str]] = [
    (r"homicides by firearm-187( victims)?", "homicides_by_firearm", "firearm"),
    (r"homicide", "homicide", "part1_violent"),
    (r"rape", "rape", "part1_violent"),
    (r"robbery", "robbery", "part1_violent"),
    (r"(aggravated )?assault", "aggravated_assault", "part1_violent"),
    (r"human trafficking\s*-\s*sex act", "human_trafficking_sex_act", "part1_violent"),
    (r"human trafficking\s*-\s*involuntary serv\.?", "human_trafficking_involuntary_servitude", "part1_violent"),
    (r"total part 1 violent crimes", "total_part1_violent", "part1_violent"),
    (r"burglary", "burglary", "part1_property"),
    (r"person/other theft\s*\*?", "person_other_theft", "part1_property"),
    (r"theft from vehicle\s*\*?", "theft_from_vehicle", "part1_property"),
    (r"larceny theft\s*\*?", "larceny_theft", "part1_property"),
    (r"(motor vehicle|auto) theft", "motor_vehicle_theft", "part1_property"),
    (r"arson", "arson", "part1_property"),
    (r"total part 1 property crimes", "total_part1_property", "part1_property"),
    (r"total part 1 crimes", "total_part1", "part1_total"),
    (r"other assaults \(misdemeanors?\):?", "other_assaults_misdemeanor", "other"),
    (r"(total )?domestic violence:?", "domestic_violence_total", "domestic_violence"),
    (r"firearms seized", "firearms_seized", "firearm"),
    (r"firearm", "dv_firearm", "domestic_violence"),
    (r"knife or other cutting instrument", "dv_knife", "domestic_violence"),
    (r"hands, fists and feet", "dv_hands_fists_feet", "domestic_violence"),
    (r"dv's without known weapons involved", "dv_no_known_weapon", "domestic_violence"),
    (r"other", "dv_other", "domestic_violence"),
    (r"non-fatal shooting incidents-217", "nonfatal_shooting_incidents", "firearm"),
    (r"non-fatal shooting victims-217", "nonfatal_shooting_victims", "firearm"),
    (r"total gun violence incidents", "total_gun_violence_incidents", "firearm"),
    (r"total shooting incidents \(217 & 187\)", "total_shooting_incidents", "firearm"),
]
# A label only counts if it is immediately followed by a number.
# "Other Assaults ..." never matches the bare "Other" pattern.
_COMPILED = [
    (re.compile(rf"^\s*{pat}\s+(?=\d)", re.IGNORECASE), cat, sec)
    for pat, cat, sec in ROW_PATTERNS
]
_INT = re.compile(r"^\d{1,3}(?:,\d{3})*$|^\d+$")

# The six count columns, in the order they appear on every row.
COUNT_COLUMNS = [
    "same_month_prior_year",
    "current_month",
    "previous_month",
    "current_month_dup",  # repeated in the month-over-month block; dropped
    "ytd_prior_year",
    "ytd_current",
]


@dataclass
class ReportLink:
    year: int
    month: int
    title: str
    url: str

    @property
    def period(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


# Extract Step:

def fetch_report_links(html: str | None = None) -> list[ReportLink]:
    """Return every monthly CompStat PDF linked from the Crime Reports page."""
    if html is None:
        resp = requests.get(REPORTS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    month_re = re.compile(
        r"(" + "|".join(MONTHS) + r")\s+(\d{4})", re.IGNORECASE
    )
    links: dict[str, ReportLink] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        text = " ".join(a.get_text(" ").split())
        if "compstat" not in text.lower() or "yearend" in text.lower():
            continue
        m = month_re.search(text)
        if not m:
            continue
        link = ReportLink(
            year=int(m.group(2)),
            month=MONTHS[m.group(1).lower()],
            title=text,
            url=urljoin(BASE_URL, href),
        )
        links.setdefault(link.period, link)  # first link wins on duplicates
    return sorted(links.values(), key=lambda l: l.period)


def download_pdf(link: ReportLink, cache_dir: Path | None = None) -> Path:
    """Download a PDF once; reuse the cached copy afterwards."""
    cache_dir = cache_dir or DATA_DIR / "raw_pdfs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"compstat_{link.period}.pdf"
    if path.exists() and path.stat().st_size > 0:
        return path
    for attempt in range(3):
        try:
            resp = requests.get(link.url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            time.sleep(1)  # be polite to the city's server
            return path
        except requests.RequestException as exc:
            log.warning("download %s failed (%s), retry %d", link.url, exc, attempt + 1)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not download {link.url}")


def pdf_page_texts(pdf_path: Path) -> list[str]:
    import pdfplumber  # imported lazily so link scraping works without it

    with pdfplumber.open(pdf_path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


# Next, Transform:

_DISTRICT_RES = [
    # "COMPSTAT - Page 2 - CENTRAL" (both layouts)
    re.compile(r"page 2\s*-\s*(" + "|".join(DISTRICTS) + r")\b", re.IGNORECASE),
    # "CENTRAL DISTRICT PROFILE" / "CITYWIDE PROFILE" (2025+) and
    # " Central Profile" (2023-era)
    re.compile(r"\b(" + "|".join(DISTRICTS) + r")\s+(?:district\s+)?profile\b", re.IGNORECASE),
]


def detect_district(page_text: str) -> str | None:
    """Work out which district a page belongs to.

    Chart captions on a page sometimes name the wrong district (copy/paste in
    the source report), so we only trust the page header/footer patterns.
    """
    for rx in _DISTRICT_RES:
        m = rx.search(page_text)
        if m:
            return m.group(1).upper()
    return None


def parse_row(line: str) -> tuple[str, str, list[int]] | None:
    """Parse one table line -> (category, section, six counts) or None."""
    for rx, cat, sec in _COMPILED:
        m = rx.match(line)
        if not m:
            continue
        rest = line[m.end():]
        rest = re.sub(r"not\s+cal", " ", rest, flags=re.IGNORECASE)
        ints = [
            int(tok.replace(",", ""))
            for tok in rest.split()
            if _INT.match(tok)  # skips "-24%", "0.4%", trailing junk words
        ]
        if len(ints) < 6:
            log.debug("short row (%d numbers): %r", len(ints), line)
            return None
        return cat, sec, ints[:6]
    return None


def parse_pages(page_texts: list[str], link: ReportLink) -> list[dict]:
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for page_no, text in enumerate(page_texts, start=1):
        district = detect_district(text)
        if district is None:
            log.debug("%s page %d: no district header, skipped", link.period, page_no)
            continue
        for line in text.splitlines():
            parsed = parse_row(line)
            if parsed is None:
                continue
            cat, sec, counts = parsed
            key = (district, cat)
            if key in seen:  # same table repeated in the PDF
                continue
            seen.add(key)
            row = dict(zip(COUNT_COLUMNS, counts))
            row.pop("current_month_dup")
            records.append(
                {
                    "report_period": link.period,
                    "report_year": link.year,
                    "report_month": link.month,
                    "district": district,
                    "section": sec,
                    "category": cat,
                    **row,
                    "source_url": link.url,
                }
            )
    return records


def validate(records: list[dict], period: str) -> list[str]:
    """Light sanity checks; returns a list of human-readable warnings."""
    warnings = []
    by_key = {(r["district"], r["category"]): r for r in records}
    districts = {r["district"] for r in records}
    missing = set(DISTRICTS) - districts
    if missing:
        warnings.append(f"{period}: missing districts {sorted(missing)}")
    for d in districts:
        v, p, t = (by_key.get((d, c)) for c in
                   ("total_part1_violent", "total_part1_property", "total_part1"))
        if v and p and t and v["current_month"] + p["current_month"] != t["current_month"]:
            warnings.append(f"{period} {d}: violent+property != total part 1")
    return warnings

# Then, Load:
def save_local(records: list[dict], out_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = out_dir or DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = out_dir / "sfpd_compstat.csv", out_dir / "sfpd_compstat.json"
    if records:
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)
    json_path.write_text(json.dumps(records, indent=2))
    return csv_path, json_path


def upload_to_gcs(records: list[dict]) -> str:
    """Upload records as JSON to the team bucket (same env vars as fast_api.py)."""
    from dotenv import load_dotenv
    from google.cloud import storage
    from google.oauth2 import service_account

    load_dotenv(".env")
    load_dotenv(".env_template")  # team convention; real values should be in .env
    key = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
    project = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCP_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not set")

    if key and Path(key).exists():
        creds = service_account.Credentials.from_service_account_file(key)
        client = storage.Client(project=project, credentials=creds)
    else:  # e.g. on Cloud Run, use the attached service account
        client = storage.Client(project=project)

    name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_crime-data.json"
    client.bucket(bucket_name).blob(name).upload_from_string(
        json.dumps(records), content_type="application/json"
    )
    return name

# Orchestration
def scrape(since: str | None = None, latest: bool = False) -> tuple[list[dict], list[str]]:
    """Run extract + transform. Returns (records, warnings)."""
    links = fetch_report_links()
    if since:
        links = [l for l in links if l.period >= since]
    if latest and links:
        links = links[-1:]
    log.info("processing %d report(s)", len(links))

    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    all_records, warnings = [], []
    for link in links:
        try:
            pages = pdf_page_texts(download_pdf(link))
        except Exception as exc:  # one bad PDF should not kill the run
            warnings.append(f"{link.period}: failed ({exc})")
            continue
        recs = parse_pages(pages, link)
        for r in recs:
            r["scraped_at"] = scraped_at
        warnings += validate(recs, link.period)
        log.info("%s: %d rows", link.period, len(recs))
        all_records += recs
    return all_records, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=os.getenv("CRIME_SINCE", "2023-01"),
                    help="earliest report month YYYY-MM (default 2023-01)")
    ap.add_argument("--latest", action="store_true", help="only the newest report")
    ap.add_argument("--upload", action="store_true", help="also upload JSON to GCS")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    # Root stays at INFO; -v only makes *our* logger verbose. pdfminer
    # (used by pdfplumber) logs every PDF drawing op at DEBUG, and warns about
    # missing FontBBox metadata in the Power BI PDFs (harmless), so keep it quiet.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("pdfminer").setLevel(logging.ERROR)

    records, warnings = scrape(since=args.since, latest=args.latest)
    for w in warnings:
        log.warning(w)
    csv_path, json_path = save_local(records)
    log.info("wrote %d rows -> %s, %s", len(records), csv_path, json_path)
    if args.upload:
        log.info("uploaded gs://%s/%s", os.getenv("GCP_BUCKET_NAME"), upload_to_gcs(records))


if __name__ == "__main__":
    main()
