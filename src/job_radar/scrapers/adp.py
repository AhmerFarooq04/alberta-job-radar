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


class ADPScraper(BaseScraper):
    BASE_URL = (
        "https://workforcenow.adp.com/"
        "mascsr/default"
    )
    PAGE_SIZE = 20

    def __init__(self, company):
        super().__init__(company)

        ats = company["ats"]

        self.cid = ats["cid"]
        self.cc_id = ats.get(
            "cc_id",
            "19000101_000001",
        )
        self.locale = ats.get(
            "locale",
            "en_CA",
        )

        self.endpoint = (
            f"{self.BASE_URL}/careercenter/"
            "public/events/staffing/v1/"
            "job-requisitions"
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": self.locale,
        })

    def fetch_jobs(self):
        postings = self._fetch_postings()
        jobs = []

        for posting in postings:
            location = self._location(posting)
            employment_type = self._type(
                posting
            )

            if self.company.get(
                "prefilter_enabled",
                True,
            ):
                if not passes_prefilter_values(
                    title=posting.get(
                        "requisitionTitle"
                    ),
                    location=location,
                    employment_type=employment_type,
                    include_internships=self.company.get(
                        "include_internships",
                        False,
                    ),
                ):
                    continue

            jobs.append(
                self._normalize(
                    posting,
                    location,
                    employment_type,
                )
            )

        return jobs

    def _fetch_postings(self):
        postings = []
        seen_ids = set()
        skip = 1

        while True:
            response = self.session.get(
                self.endpoint,
                params={
                    "cid": self.cid,
                    "ccId": self.cc_id,
                    "$top": self.PAGE_SIZE,
                    "$skip": skip,
                },
                timeout=30,
            )
            response.raise_for_status()

            page = response.json().get(
                "jobRequisitions",
                [],
            )

            if not isinstance(page, list):
                raise ValueError(
                    f"Invalid ADP response: "
                    f"{self.company['name']}"
                )

            if not page:
                break

            for posting in page:
                job_id = posting.get("itemID")

                if not job_id:
                    continue

                if job_id in seen_ids:
                    continue

                seen_ids.add(job_id)
                postings.append(posting)

            if len(page) < self.PAGE_SIZE:
                break

            skip += len(page)

        return postings

    def _normalize(
        self,
        posting,
        location,
        employment_type,
    ):
        job_id = str(posting["itemID"])

        job_url = (
            f"{self.BASE_URL}/mdf/recruitment/"
            f"recruitment.html?cid={self.cid}"
            f"&ccId={self.cc_id}"
            f"&jobId={job_id}"
            f"&lang={self.locale}"
        )

        description = (
            posting.get("jobDescription")
            or posting.get(
                "requisitionDescription"
            )
            or posting.get("description")
            or ""
        )

        return Job(
            external_id=job_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get(
                "requisitionTitle",
                "Unknown title",
            ),
            location=location,
            description=html_to_text(
                description
            ),
            job_url=job_url,
            source="adp",
            posted_at=parse_date(
                posting.get("postDate")
            ),
            employment_type=employment_type,
        )

    @staticmethod
    def _location(posting):
        locations = []

        for location in (
            posting.get(
                "requisitionLocations"
            )
            or []
        ):
            name_code = (
                location.get("nameCode")
                or {}
            )

            value = name_code.get(
                "shortName"
            )

            if value and value not in locations:
                locations.append(value)

        return (
            "; ".join(locations)
            or "Not specified"
        )

    @staticmethod
    def _type(posting):
        value = (
            posting.get("workerTypeCode")
            or {}
        )

        if isinstance(value, dict):
            return (
                value.get("shortName")
                or value.get("codeValue")
            )

        return str(value) if value else None