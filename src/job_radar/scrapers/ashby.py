from datetime import datetime

import requests

from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper


def parse_iso_datetime(
    value: str | None,
) -> datetime | None:
    """Parse an ISO 8601 timestamp."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


class AshbyScraper(BaseScraper):
    API_URL = (
        "https://api.ashbyhq.com/"
        "posting-api/job-board/{board}"
    )

    def fetch_jobs(self) -> list[Job]:
        board = self.company["ats"]["board"]

        response = requests.get(
            self.API_URL.format(board=board),
            params={
                "includeCompensation": "false",
            },
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
                f"Ashby returned invalid job data for "
                f"{self.company['name']}"
            )

        jobs = []

        for posting in postings:
            # Unlisted postings may remain accessible through a direct
            # URL, but should not appear in public search results.
            if not posting.get("isListed", True):
                continue

            jobs.append(
                self._convert_posting(posting)
            )

        return jobs

    def _convert_posting(
        self,
        posting: dict,
    ) -> Job:
        job_url = (
            posting.get("jobUrl")
            or posting.get("applyUrl")
            or ""
        )

        external_id = job_url

        if not external_id:
            external_id = (
                f"{posting.get('title', 'unknown')}:"
                f"{posting.get('location', 'unknown')}"
            )

        return Job(
            external_id=external_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get(
                "title",
                "Unknown title",
            ),
            location=posting.get(
                "location",
                "Not specified",
            ),
            description=posting.get(
                "descriptionPlain",
                "",
            ),
            job_url=job_url,
            source="ashby",
            posted_at=parse_iso_datetime(
                posting.get("publishedAt")
            ),
            employment_type=posting.get(
                "employmentType"
            ),
            workplace_type=posting.get(
                "workplaceType"
            ),
        )