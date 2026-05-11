from __future__ import annotations

from datetime import datetime, timezone


SOURCE = "Federal Reserve"


def get_fed_public_sources() -> list[dict]:
    timestamp = datetime.now(timezone.utc).isoformat()

    return [
        {
            "name": "Federal Reserve Press Releases",
            "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
            "type": "official_source",
            "source": SOURCE,
            "timestamp": timestamp,
            "status": "ok",
            "error": None,
        },
        {
            "name": "Federal Reserve Speeches",
            "url": "https://www.federalreserve.gov/newsevents/speeches.htm",
            "type": "official_source",
            "source": SOURCE,
            "timestamp": timestamp,
            "status": "ok",
            "error": None,
        },
        {
            "name": "FOMC Meeting Calendars and Statements",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "type": "official_source",
            "source": SOURCE,
            "timestamp": timestamp,
            "status": "ok",
            "error": None,
        },
    ]
