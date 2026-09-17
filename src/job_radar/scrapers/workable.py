import re
from datetime import datetime

import requests

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def markdown_to_text(value):
    value = re.sub(
        r"!\[[^]]*]\([^)]*\)",
        " ",
        value,
    )
    value = re.sub(
        r"\[([^]]+)]\([^)]*\)",
        r"\1",
        value,
    )
    value = re.sub(
        r"^\s{0,3}(?:#{1,6}|>|[-*+]\s)\s*",
        "",
        value,
        flags=re.MULTILINE,
    )
    value = re.sub(r"[*_`~]", "", value)

    return " ".join(value.split())


class WorkableScraper(BaseScraper):
    BASE_URL = "https://apply.workable.com"

    def __init__(self, company):
        super().__init__(company)

        self.account = company["ats"]["account"]

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
        })

    def fetch_jobs(self):
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
                    title=summary.get("title"),
                    location=self._location(summary),
                    employment_type=summary.get("type"),
                    include_internships=include_internships,
                )
            ]

        max_jobs = self.company.get("max_jobs")

        if max_jobs is not None:
            summaries = summaries[:max_jobs]

        return [
            self._normalize(summary)
            for summary in summaries
        ]

    def _fetch_summaries(self):
        response = self.session.post(
            (
                f"{self.BASE_URL}/api/v3/accounts/"
                f"{self.account}/jobs"
            ),
            json={
                "query": "",
                "department": [],
                "location": [],
                "workplace": [],
                "worktype": [],
            },
            timeout=30,
        )
        response.raise_for_status()

        results = response.json().get("results", [])

        if not isinstance(results, list):
            raise ValueError(
                f"Invalid Workable response: "
                f"{self.company['name']}"
            )

        return [
            result
            for result in results
            if result.get("shortcode")
        ]

    def _normalize(self, summary):
        shortcode = str(summary["shortcode"])

        job_url = (
            f"{self.BASE_URL}/{self.account}/"
            f"j/{shortcode}/"
        )

        markdown_url = (
            f"{self.BASE_URL}/{self.account}/"
            f"jobs/view/{shortcode}.md"
        )

        response = self.session.get(
            markdown_url,
            timeout=30,
        )
        response.raise_for_status()

        workplace = summary.get("workplace")

        return Job(
            external_id=shortcode,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=summary.get(
                "title",
                "Unknown title",
            ),
            location=self._location(summary),
            description=markdown_to_text(
                response.text
            ),
            job_url=job_url,
            source="workable",
            posted_at=parse_date(
                summary.get("published")
            ),
            employment_type=summary.get("type"),
            workplace_type=(
                workplace.replace("_", " ").title()
                if workplace
                else None
            ),
        )

    @staticmethod
    def _location(summary):
        location = summary.get("location") or {}

        parts = [
            location.get("city"),
            location.get("region"),
            location.get("country"),
        ]

        value = ", ".join(
            part
            for part in parts
            if part
        )

        if summary.get("remote"):
            return (
                f"Remote — {value}"
                if value
                else "Remote"
            )

        return value or "Not specified"