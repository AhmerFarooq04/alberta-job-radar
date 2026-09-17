from datetime import datetime

import requests

from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper, html_to_text


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp when one is available."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


class GreenhouseScraper(BaseScraper):
    API_URL = (
        "https://boards-api.greenhouse.io/"
        "v1/boards/{board}/jobs"
    )

    def fetch_jobs(self) -> list[Job]:
        board = self.company["ats"]["board"]

        response = requests.get(
            self.API_URL.format(board=board),
            params={"content": "true"},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; AlbertaJobRadar/0.1)"
                )
            },
            timeout=30,
        )

        response.raise_for_status()

        response_data = response.json()
        postings = response_data.get("jobs", [])

        if not isinstance(postings, list):
            raise ValueError(
                f"Greenhouse returned invalid jobs data for "
                f"{self.company['name']}"
            )

        return [
            self._convert_posting(posting)
            for posting in postings
        ]

    def _convert_posting(self, posting: dict) -> Job:
        location_data = posting.get("location") or {}

        return Job(
            external_id=str(posting["id"]),
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get("title", "Unknown title"),
            location=location_data.get(
                "name",
                "Not specified",
            ),
            description=html_to_text(
                posting.get("content", "")
            ),
            job_url=posting.get("absolute_url", ""),
            source="greenhouse",
            posted_at=parse_iso_datetime(
                posting.get("first_published")
            ),
        )