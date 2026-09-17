import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper, html_to_text


class HtmlBoardScraper(BaseScraper):
    def __init__(self, company):
        super().__init__(company)

        ats = company["ats"]

        self.listing_url = ats["listing_url"]
        self.link_pattern = re.compile(
            ats["link_pattern"]
        )
        self.title_selector = ats[
            "title_selector"
        ]
        self.description_selector = ats[
            "description_selector"
        ]

        self.location_regex = (
            re.compile(
                ats["location_regex"]
            )
            if ats.get("location_regex")
            else None
        )

        self.employment_regex = (
            re.compile(
                ats["employment_regex"]
            )
            if ats.get("employment_regex")
            else None
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; "
                "Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            )
        })

    def fetch_jobs(self):
        response = self.session.get(
            self.listing_url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        links = []
        seen = set()

        for anchor in soup.find_all(
            "a",
            href=True,
        ):
            url = urljoin(
                response.url,
                anchor["href"],
            )

            if not self.link_pattern.search(url):
                continue

            if url in seen:
                continue

            seen.add(url)
            links.append(url)

        jobs = []

        for url in links:
            job = self._fetch_job(url)

            if job is None:
                continue

            if self.company.get(
                "prefilter_enabled",
                True,
            ):
                if not passes_prefilter_values(
                    title=job.title,
                    location=job.location,
                    employment_type=job.employment_type,
                    include_internships=self.company.get(
                        "include_internships",
                        False,
                    ),
                ):
                    continue

            jobs.append(job)

        return jobs

    def _fetch_job(self, url):
        response = self.session.get(
            url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        title_element = soup.select_one(
            self.title_selector
        )
        description_element = soup.select_one(
            self.description_selector
        )

        if (
            title_element is None
            or description_element is None
        ):
            return None

        page_text = soup.get_text(
            " ",
            strip=True,
        )

        location = self._match(
            page_text,
            self.location_regex,
        )

        employment_type = self._match(
            page_text,
            self.employment_regex,
        )

        job_id = (
            urlparse(response.url)
            .path.rstrip("/")
            .split("/")[-1]
        )

        return Job(
            external_id=job_id,
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=title_element.get_text(
                " ",
                strip=True,
            ),
            location=(
                location
                or "Not specified"
            ),
            description=html_to_text(
                str(description_element)
            ),
            job_url=response.url,
            source="html_board",
            employment_type=employment_type,
        )

    @staticmethod
    def _match(text, pattern):
        if pattern is None:
            return None

        match = pattern.search(text)

        if match is None:
            return None

        if match.groups():
            return match.group(1)

        return match.group(0)