"""
FastAPI router for the SFPD scraper.

The FastAPI owner can plug this into fast_api:

    from scraping.crime_router import router as crime_router
    app.include_router(crime_router)

Cloud Scheduler then calls:  POST /crime-data?latest=true   (calls monthly)
A one-time backfill:         POST /crime-data?since=2023-01
"""

from fastapi import APIRouter, HTTPException

from scraping.sfpd_scraper import scrape, upload_to_gcs

router = APIRouter()


@router.post("/crime-data")
def send_crime_data_to_bucket(since: str | None = None, latest: bool = True):
    # An explicit `since` means backfill, so it overrides latest-only.
    records, warnings = scrape(since=since, latest=latest and since is None)
    if not records:
        raise HTTPException(status_code=502, detail={"message": "no rows parsed", "warnings": warnings})
    file_name = upload_to_gcs(records)
    return {
        "message": "Crime data uploaded successfully",
        "file_name": file_name,
        "rows": len(records),
        "periods": sorted({r["report_period"] for r in records}),
        "warnings": warnings,
    }
