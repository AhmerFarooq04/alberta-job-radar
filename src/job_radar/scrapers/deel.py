import json

import requests
from bs4 import BeautifulSoup

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper, html_to_text
from job_radar.scrapers.jsonld import parse_date


class DeelScraper(BaseScraper):
    def __init__(self, company):
        super().__init__(company)

        self.slug = company["ats"]["slug"]
        self.board_url = (
            f"https://jobs.deel.com/{self.slug}"
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
        })

    def fetch_jobs(self):
        summaries = self._fetch_summaries()
        jobs = []

        for summary in summaries:
            location = self._location(summary)
            employment_type = self._type(
                summary
            )

            if self.company.get(
                "prefilter_enabled",
                True,
            ):
                if not passes_prefilter_values(
                    title=summary.get("title"),
                    location=location,
                    employment_type=employment_type,
                    include_internships=self.company.get(
                        "include_internships",
                        False,
                    ),
                ):
                    continue

            jobs.append(
                self._fetch_detail(
                    summary,
                    location,
                    employment_type,
                )
            )

        return jobs

    def _fetch_summaries(self):
        response = self.session.get(
            self.board_url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        chunks = []

        for script in soup.find_all("script"):
            value = (
                script.string
                or script.get_text()
            )

            marker = "self.__next_f.push("

            if marker not in value:
                continue

            try:
                item = json.loads(
                    value.split(
                        marker,
                        1,
                    )[1].rsplit(
                        ")",
                        1,
                    )[0]
                )
            except (IndexError, ValueError):
                continue

            if (
                len(item) > 1
                and isinstance(item[1], str)
            ):
                chunks.append(item[1])

        stream = "".join(chunks)
        marker = '"jobPostings":'
        position = stream.find(marker)

        if position < 0:
            raise ValueError(
                f"Deel job data unavailable: "
                f"{self.company['name']}"
            )

        postings, _ = (
            json.JSONDecoder().raw_decode(
                stream[
                    position + len(marker):
                ]
            )
        )

        return postings

    def _fetch_detail(
        self,
        summary,
        location,
        employment_type,
    ):
        job_id = str(summary["id"])

        url = (
            f"{self.board_url}/job-details/"
            f"{job_id}/overview"
        )

        response = self.session.get(
            url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        posting = None

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):
            try:
                candidate = json.loads(
                    script.string
                    or script.get_text()
                )
            except (TypeError, ValueError):
                continue

            if (
                candidate.get("@type")
                == "JobPosting"
            ):
                posting = candidate
                break

        if posting is None:
            raise ValueError(
                f"Missing Deel details: {job_id}"
            )

        return Job(
            external_id=job_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=(
                posting.get("title")
                or summary.get("title")
            ),
            location=location,
            description=html_to_text(
                posting.get("description", "")
            ),
            job_url=url,
            source="deel",
            posted_at=parse_date(
                posting.get("datePosted")
                or summary.get("createdAt")
            ),
            employment_type=(
                posting.get("employmentType")
                or employment_type
            ),
            workplace_type=self._workplace(
                summary
            ),
        )

    @staticmethod
    def _location(summary):
        locations = []

        job = summary.get("job") or {}

        for item in (
            job.get("jobLocations")
            or []
        ):
            location = (
                item.get("location")
                or {}
            )

            name = location.get("name")

            if name and name not in locations:
                locations.append(name)

        return (
            "; ".join(locations)
            or "Not specified"
        )

    @staticmethod
    def _type(summary):
        types = []
        job = summary.get("job") or {}

        for item in (
            job.get("jobEmploymentTypes")
            or []
        ):
            value = (
                item.get("employmentType")
                or {}
            ).get("name")

            if value and value not in types:
                types.append(value)

        return ", ".join(types) or None

    @staticmethod
    def _workplace(summary):
        value = (
            summary.get("job")
            or {}
        ).get("workArrangementEnum")

        if not value:
            return None

        return value.replace(
            "_",
            " ",
        ).title()