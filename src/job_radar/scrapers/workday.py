import time
from urllib.parse import urljoin

import requests

from job_radar.filters import (
    passes_prefilter_values,
)
from job_radar.models import Job
from job_radar.scrapers.base import (
    BaseScraper,
    html_to_text,
)


class WorkdayScraper(BaseScraper):
    PAGE_SIZE = 20

    def __init__(self, company: dict):
        super().__init__(company)

        ats = company["ats"]

        self.host = ats["host"]
        self.tenant = ats["tenant"]
        self.site = ats["site"]
        self.locale = ats.get(
            "locale",
            "en-US",
        )

        self.api_base_url = (
            f"https://{self.host}/wday/cxs/"
            f"{self.tenant}/{self.site}"
        )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; AlbertaJobRadar/0.1)"
                ),
                "Accept": "application/json",
                "Accept-Language": (
                    "en-CA,en;q=0.9"
                ),
            }
        )

    def fetch_jobs(self) -> list[Job]:
        """
        Retrieve summaries, prefilter them, and download full details
        only for potentially relevant jobs.
        """

        summaries = self._fetch_all_summaries()

        prefilter_enabled = self.company.get(
            "prefilter_enabled",
            True,
        )

        if prefilter_enabled:
            include_internships = self.company.get(
                "include_internships",
                False,
            )

            summaries = [
                summary
                for summary in summaries
                if passes_prefilter_values(
                    title=summary.get("title"),
                    location=summary.get(
                        "locationsText"
                    ),
                    employment_type=summary.get(
                        "timeType"
                    ),
                    include_internships=(
                        include_internships
                    ),
                )
            ]

        # Used for live smoke testing. Production company entries
        # should normally omit max_jobs.
        max_jobs = self.company.get("max_jobs")

        if max_jobs is not None:
            summaries = summaries[:max_jobs]

        jobs = []

        detail_delay = self.company.get(
            "detail_delay_seconds",
            0.25,
        )

        for summary in summaries:
            job = self._fetch_job_detail(
                summary
            )
            jobs.append(job)

            time.sleep(detail_delay)

        return jobs

    def _fetch_all_summaries(
        self,
    ) -> list[dict]:
        """Retrieve every page of Workday job summaries."""

        jobs_url = f"{self.api_base_url}/jobs"

        all_summaries = []
        seen_paths = set()
        offset = 0
        total = None

        while total is None or offset < total:
            payload = {
                "appliedFacets": {},
                "limit": self.PAGE_SIZE,
                "offset": offset,
                "searchText": "",
            }

            response = self.session.post(
                jobs_url,
                json=payload,
                timeout=30,
            )

            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError as error:
                raise ValueError(
                    "Workday returned non-JSON data for "
                    f"{self.company['name']}"
                ) from error

            page_summaries = response_data.get(
                "jobPostings",
                [],
            )

            if not isinstance(
                page_summaries,
                list,
            ):
                raise ValueError(
                    "Workday returned invalid "
                    "jobPostings data for "
                    f"{self.company['name']}"
                )

            raw_total = response_data.get(
                "total",
                len(page_summaries),
            )

            try:
                total = int(raw_total)
            except (TypeError, ValueError):
                total = len(page_summaries)

            if not page_summaries:
                break

            for summary in page_summaries:
                external_path = summary.get(
                    "externalPath"
                )

                if not external_path:
                    continue

                if external_path in seen_paths:
                    continue

                seen_paths.add(external_path)
                all_summaries.append(summary)

            offset += len(page_summaries)

        return all_summaries

    def _fetch_job_detail(
        self,
        summary: dict,
    ) -> Job:
        """Retrieve and normalize one complete Workday job."""

        external_path = summary["externalPath"]
        detail_url = (
            f"{self.api_base_url}{external_path}"
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
                "Workday returned non-JSON details for "
                f"{self.company['name']}: "
                f"{external_path}"
            ) from error

        job_info = response_data.get(
            "jobPostingInfo",
            {},
        )

        if not isinstance(job_info, dict):
            raise ValueError(
                "Workday returned invalid job details for "
                f"{self.company['name']}: "
                f"{external_path}"
            )

        direct_job_url = job_info.get(
            "externalUrl"
        )

        if direct_job_url:
            direct_job_url = urljoin(
                f"https://{self.host}",
                direct_job_url,
            )
        else:
            direct_job_url = (
                f"https://{self.host}/"
                f"{self.locale}/{self.site}"
                f"{external_path}"
            )

        title = (
            job_info.get("title")
            or summary.get("title")
            or "Unknown title"
        )

        location = (
            job_info.get("location")
            or summary.get("locationsText")
            or "Not specified"
        )

        description_html = job_info.get(
            "jobDescription",
            "",
        )

        posted_text = (
            job_info.get("postedOn")
            or summary.get("postedOn")
        )

        external_id = (
            job_info.get("jobReqId")
            or job_info.get("jobPostingId")
            or external_path
        )

        employment_type = (
            job_info.get("timeType")
            or summary.get("timeType")
        )

        workplace_type = (
            job_info.get("remoteType")
            or summary.get("remoteType")
        )

        return Job(
            external_id=str(external_id),
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=title,
            location=location,
            description=html_to_text(
                description_html
            ),
            job_url=direct_job_url,
            source="workday",
            posted_at=None,
            posted_text=posted_text,
            employment_type=employment_type,
            workplace_type=workplace_type,
        )