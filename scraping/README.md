# SFPD Crime Reports Scraper — Brendan Waterval

Source: <https://www.sanfranciscopolice.org/stay-safe/crime-data/crime-reports>

- The page is static HTML listing one CompStat PDF per month, from 2015 to present.
  `requests` and `BeautifulSoup` get the links; we do not need Playwright.
- The numbers are **inside the PDFs**. Each PDF has 2 pages per district
  (Citywide + 10 police districts): page 1 = Part 1 crimes, page 2 = domestic violence + firearms.
- Every table row has 6 counts: same month last year, this month, last month, this month (repeat),
  YTD last year, YTD this year. Percent columns are skipped because they're blank when the base is 0
  and sometimes wrap onto other lines. They can be recomputed from the counts.
- Two layouts are handled: the 2025+ Power BI layout and the 2023-era layout (where the
  district name is printed *after* the table). Category names are normalized across both like `AUTO THEFT` / `Motor Vehicle Theft` into `motor_vehicle_theft`.

## Output

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

These are police districts, not supervisor districts (might be a future concern).

## Run

```bash
bash scraping/run_scraper.sh                    
bash scraping/run_scraper.sh --latest           # newest month only
bash scraping/run_scraper.sh --since 2025-01 --upload  # also uploads to bucket
```

`--upload` uses the same env vars as `fast_api/fast_api.py`:
`GCP_SERVICE_ACCOUNT_KEY`, `GCP_PROJECT_ID`, `GCP_BUCKET_NAME`.

## FastAPI integration

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
