import time
from datetime import datetime

import requests

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import (
    BaseScraper,
    html_to_text,
)


def parse_posted_date(
    value: str | None,
) -> datetime | None:
    """Parse BambooHR's YYYY-MM-DD posting date."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class BambooHRScraper(BaseScraper):
    """Read jobs from a public BambooHR careers board."""

    def __init__(self, company: dict):
        super().__init__(company)

        subdomain = company["ats"]["subdomain"]
        self.careers_url = (
            f"https://{subdomain}.bamboohr.com/careers"
        )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; AlbertaJobRadar/0.1)"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-CA,en;q=0.9",
            }
        )

    def fetch_jobs(self) -> list[Job]:
        """Download summaries and relevant full job descriptions."""

        summaries = self._fetch_summaries()

        if self.company.get("prefilter_enabled", True):
            include_internships = self.company.get(
                "include_internships",
                False,
            )

            summaries = [
                summary
                for summary in summaries
                if passes_prefilter_values(
                    title=summary.get("jobOpeningName"),
                    location=self._format_location(summary),
                    employment_type=(
                        summary.get("employmentStatusLabel")
                        or summary.get("employmentType")
                    ),
                    include_internships=include_internships,
                )
            ]

        max_jobs = self.company.get("max_jobs")

        if max_jobs is not None:
            summaries = summaries[:max_jobs]

        jobs = []
        detail_delay = self.company.get(
            "detail_delay_seconds",
            0.25,
        )

        for position, summary in enumerate(summaries):
            jobs.append(self._fetch_job_detail(summary))

            if position < len(summaries) - 1:
                time.sleep(detail_delay)

        return jobs

    def _fetch_summaries(self) -> list[dict]:
        response = self.session.get(
            f"{self.careers_url}/list",
            timeout=30,
        )
        response.raise_for_status()

        try:
            response_data = response.json()
        except ValueError as error:
            raise ValueError(
                "BambooHR returned non-JSON job summaries for "
                f"{self.company['name']}"
            ) from error

        summaries = response_data.get("result", [])

        if not isinstance(summaries, list):
            raise ValueError(
                "BambooHR returned invalid job summaries for "
                f"{self.company['name']}"
            )

        return [
            summary
            for summary in summaries
            if isinstance(summary, dict) and summary.get("id")
        ]

    def _fetch_job_detail(self, summary: dict) -> Job:
        external_id = str(summary["id"])
        detail_url = (
            f"{self.careers_url}/{external_id}/detail"
        )

        response = self.session.get(
            detail_url,
            timeout=30,
        )
        response.raise_for_status()

        try:
            response_data = response.json()
        except ValueError as error:
            raise ValueError(
                "BambooHR returned non-JSON job details for "
                f"{self.company['name']}: {external_id}"
            ) from error

        result = response_data.get("result", {})
        job_opening = result.get("jobOpening", {})

        if not isinstance(job_opening, dict):
            raise ValueError(
                "BambooHR returned invalid job details for "
                f"{self.company['name']}: {external_id}"
            )

        merged_posting = {
            **summary,
            **job_opening,
        }

        job_url = (
            job_opening.get("jobOpeningShareUrl")
            or f"{self.careers_url}/{external_id}"
        )

        is_remote = bool(merged_posting.get("isRemote"))

        return Job(
            external_id=external_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=merged_posting.get(
                "jobOpeningName",
                "Unknown title",
            ),
            location=self._format_location(merged_posting),
            description=html_to_text(
                job_opening.get("description", "")
            ),
            job_url=job_url,
            source="bamboohr",
            posted_at=parse_posted_date(
                job_opening.get("datePosted")
            ),
            employment_type=(
                merged_posting.get("employmentStatusLabel")
                or merged_posting.get("employmentType")
            ),
            workplace_type=(
                "Remote" if is_remote else None
            ),
        )

    @staticmethod
    def _format_location(posting: dict) -> str:
        """Build one useful location from BambooHR's location objects."""

        location = posting.get("location") or {}
        ats_location = posting.get("atsLocation") or {}

        if not isinstance(location, dict):
            location = {}

        if not isinstance(ats_location, dict):
            ats_location = {}

        candidates = [
            location.get("city") or ats_location.get("city"),
            location.get("state")
            or location.get("province")
            or ats_location.get("state")
            or ats_location.get("province"),
            location.get("addressCountry")
            or location.get("country")
            or ats_location.get("country"),
        ]

        parts = []

        for value in candidates:
            if not value:
                continue

            cleaned_value = str(value).strip()

            if cleaned_value and cleaned_value not in parts:
                parts.append(cleaned_value)

        location_text = ", ".join(parts)
        is_remote = bool(posting.get("isRemote"))

        if is_remote and location_text:
            return f"Remote — {location_text}"

        if is_remote:
            return "Remote"

        return location_text or "Not specified"