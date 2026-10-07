# SFPD Crime Reports Scraper (scraping branch — Brendan)

Source: <https://www.sanfranciscopolice.org/stay-safe/crime-data/crime-reports>

## How the source works

- The page is **static HTML** (Drupal) listing one CompStat PDF per month, 2015 → present.
  `requests` + `BeautifulSoup` gets the links; no Playwright needed.
- The numbers are **inside the PDFs**. Each PDF has 2 pages per district
  (Citywide + 10 police districts): page 1 = Part 1 crimes, page 2 = domestic violence + firearms.
- Every table row has 6 counts: same month last year, this month, last month, this month (repeat),
  YTD last year, YTD this year. Percent columns are skipped (they're blank when the base is 0
  and sometimes wrap onto other lines). They can be recomputed from the counts.
- Two layouts are handled: the 2025+ Power BI layout and the 2023-era layout (where the
  district name is printed *after* the table). Category names are normalized across both,
  e.g. `AUTO THEFT` / `Motor Vehicle Theft` → `motor_vehicle_theft`.

## Output (long / tidy format)

One row per `report_period × district × category`:

| column | example |
|---|---|
| report_period, report_year, report_month | 2026-08, 2026, 8 |
| district | CENTRAL (CITYWIDE + 10 SFPD districts) |
| section | part1_violent, part1_property, part1_total, other, domestic_violence, firearm |
| category | robbery, larceny_theft, firearms_seized, ... |
| current_month, same_month_prior_year, previous_month | 17, 16, 16 |
| ytd_current, ytd_prior_year | 104, 131 |
| source_url, scraped_at | PDF link, UTC timestamp |

Note: these are **police districts**, not supervisor districts — joining to tree/census data
will need a crosswalk or a spatial join (flag for cleaning/EDA).

## Run

```bash
bash scraping/run_scraper.sh                    # backfill from 2023-01 → scraping/data/
bash scraping/run_scraper.sh --latest           # newest month only
bash scraping/run_scraper.sh --since 2025-01 --upload   # also write JSON to the GCS bucket
```

`--upload` uses the same env vars as `fast_api/fast_api.py`:
`GCP_SERVICE_ACCOUNT_KEY`, `GCP_PROJECT_ID`, `GCP_BUCKET_NAME`.

## FastAPI integration (for the fastapi branch)

```python
from scraping.crime_router import router as crime_router
app.include_router(crime_router)
```

- `POST /crime-data` → scrapes the newest report and uploads `<timestamp>_crime-data.json`
- `POST /crime-data?since=2023-01` → backfill
- Cloud Scheduler: monthly (reports post ~3–6 weeks after month end), e.g. `0 9 10 * *`.

## Tests

`python -m pytest scraping/tests -q` — fixtures are text copied from the real Aug 2026 and
Jan 2023 PDFs.

## Known gaps / TODO

- Pre-2023 PDFs use other layouts; they'll show up as "missing districts" warnings.
- Verify `pdfplumber` line output against the fixtures on a few real PDFs (`-v` flag logs skipped rows).
- Duplicate-proofing in the bucket (currently each run writes a new timestamped file).
