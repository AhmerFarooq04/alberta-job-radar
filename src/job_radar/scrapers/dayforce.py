from datetime import datetime

import requests

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper, html_to_text


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


class DayforceScraper(BaseScraper):
    BASE_URL = "https://jobs.dayforcehcm.com"
    PAGE_SIZE = 200

    def __init__(self, company):
        super().__init__(company)

        ats = company["ats"]
        self.namespace = ats["namespace"]
        self.board = ats["board"]
        self.culture = ats.get("culture", "en-US")

        self.board_url = (
            f"{self.BASE_URL}/{self.culture}/"
            f"{self.namespace}/{self.board}"
        )

        self.search_url = (
            f"{self.BASE_URL}/api/geo/{self.namespace}/"
            "jobposting/search"
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": self.board_url,
        })

    def fetch_jobs(self):
        postings = self._fetch_postings()

        if self.company.get("prefilter_enabled", True):
            include_internships = self.company.get(
                "include_internships",
                False,
            )

            postings = [
                posting
                for posting in postings
                if passes_prefilter_values(
                    title=posting.get("jobTitle"),
                    location=self._location(posting),
                    employment_type=posting.get(
                        "employmentType"
                    ),
                    include_internships=include_internships,
                )
            ]

        max_jobs = self.company.get("max_jobs")

        if max_jobs is not None:
            postings = postings[:max_jobs]

        return [
            self._normalize(posting)
            for posting in postings
        ]

    def _fetch_postings(self):
        csrf_response = self.session.get(
            f"{self.BASE_URL}/api/auth/csrf",
            timeout=30,
        )
        csrf_response.raise_for_status()

        csrf_token = csrf_response.json().get("csrfToken")

        if not csrf_token:
            raise ValueError(
                f"Invalid Dayforce CSRF response: "
                f"{self.company['name']}"
            )

        postings = []
        seen_ids = set()
        page_number = 1
        total = None

        while total is None or len(postings) < total:
            response = self.session.post(
                self.search_url,
                json={
                    "clientNamespace": self.namespace,
                    "jobBoardCode": self.board,
                    "cultureCode": self.culture,
                    "pageNumber": page_number,
                    "pageSize": self.PAGE_SIZE,
                },
                headers={
                    "X-CSRF-TOKEN": csrf_token,
                },
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            page = data.get("jobPostings", [])

            if not isinstance(page, list):
                raise ValueError(
                    f"Invalid Dayforce response: "
                    f"{self.company['name']}"
                )

            total = int(data.get("maxCount", len(page)))

            if not page:
                break

            added = 0

            for posting in page:
                job_id = posting.get("jobPostingId")

                if not job_id or job_id in seen_ids:
                    continue

                seen_ids.add(job_id)
                postings.append(posting)
                added += 1

            if added == 0:
                break

            page_number += 1

        return postings

    def _normalize(self, posting):
        job_id = str(posting["jobPostingId"])

        return Job(
            external_id=job_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get(
                "jobTitle",
                "Unknown title",
            ),
            location=self._location(posting),
            description=html_to_text(
                posting.get("jobDescription", "")
            ),
            job_url=(
                f"{self.board_url}/jobs/{job_id}"
            ),
            source="dayforce",
            posted_at=parse_date(
                posting.get(
                    "postingStartTimestampUTC"
                )
            ),
            employment_type=posting.get(
                "employmentType"
            ),
            workplace_type=(
                "Remote"
                if posting.get("hasVirtualLocation")
                else None
            ),
        )

    @staticmethod
    def _location(posting):
        locations = []

        for location in (
            posting.get("postingLocations") or []
        ):
            value = location.get("formattedAddress")

            if not value:
                value = ", ".join(
                    part
                    for part in (
                        location.get("cityName"),
                        location.get("stateCode"),
                        location.get("isoCountryCode"),
                    )
                    if part
                )

            if value and value not in locations:
                locations.append(value)

        result = (
            "; ".join(locations)
            or "Not specified"
        )

        if posting.get("hasVirtualLocation"):
            if result == "Not specified":
                return "Remote"

            return f"Remote — {result}"

        return result