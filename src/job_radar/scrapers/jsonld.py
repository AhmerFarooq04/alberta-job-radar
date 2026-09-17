import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import (
    BaseScraper,
    html_to_text,
)


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


class JsonLdScraper(BaseScraper):
    def __init__(self, company):
        super().__init__(company)

        ats = company["ats"]

        self.listing_url = ats["listing_url"]
        self.link_pattern = re.compile(
            ats["link_pattern"]
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; "
                "Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        })

    def fetch_jobs(self):
        links = self._fetch_links()
        jobs = []

        for link in links:
            posting = self._fetch_posting(link)

            if not posting:
                continue

            location = self._location(posting)
            employment_type = posting.get(
                "employmentType"
            )

            if isinstance(employment_type, list):
                employment_type = ", ".join(
                    employment_type
                )

            if self.company.get(
                "prefilter_enabled",
                True,
            ):
                if not passes_prefilter_values(
                    title=posting.get("title"),
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
                    link,
                    location,
                    employment_type,
                )
            )

            max_jobs = self.company.get("max_jobs")

            if (
                max_jobs is not None
                and len(jobs) >= max_jobs
            ):
                break

        return jobs

    def _fetch_links(self):
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

        return links

    def _fetch_posting(self, url):
        response = self.session.get(
            url,
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):
            try:
                value = json.loads(
                    script.string
                    or script.get_text()
                )
            except (TypeError, ValueError):
                continue

            candidates = (
                value
                if isinstance(value, list)
                else [value]
            )

            for candidate in candidates:
                if not isinstance(
                    candidate,
                    dict,
                ):
                    continue

                if (
                    candidate.get("@type")
                    == "JobPosting"
                ):
                    return candidate

        return self._microdata(
            soup,
            response.url,
        )

    @staticmethod
    def _microdata(soup, url):
        container = soup.find(
            attrs={
                "itemtype": re.compile(
                    r"schema[.]org/JobPosting"
                )
            }
        )

        if container is None:
            return None

        def content(name):
            element = container.find(
                attrs={"itemprop": name}
            )

            if element is None:
                return None

            return (
                element.get("content")
                or element.get_text(
                    " ",
                    strip=True,
                )
            )

        address = {}

        for field in (
            "addressLocality",
            "addressRegion",
            "addressCountry",
        ):
            value = content(field)

            if value:
                address[field] = value

        description = container.find(
            attrs={
                "itemprop": "description"
            }
        )

        return {
            "@type": "JobPosting",
            "url": url,
            "title": content("title"),
            "description": str(
                description or ""
            ),
            "datePosted": content("datePosted"),
            "employmentType": content(
                "employmentType"
            ),
            "jobLocation": {
                "@type": "Place",
                "address": address,
            },
        }

    def _normalize(
        self,
        posting,
        source_url,
        location,
        employment_type,
    ):
        url = posting.get("url") or source_url

        return Job(
            external_id=self._external_id(url),
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get(
                "title",
                "Unknown title",
            ),
            location=location,
            description=html_to_text(
                posting.get("description", "")
            ),
            job_url=url,
            source="jsonld",
            posted_at=parse_date(
                posting.get("datePosted")
            ),
            employment_type=employment_type,
            workplace_type=(
                "Remote"
                if posting.get("jobLocationType")
                == "TELECOMMUTE"
                else None
            ),
        )

    @staticmethod
    def _external_id(url):
        match = re.search(
            r"/jobs?/(\d+)",
            url,
        )

        if match:
            return match.group(1)

        parts = [
            part
            for part in url.rstrip("/").split("/")
            if part
        ]

        if "apply" in parts:
            position = parts.index("apply")

            if position + 1 < len(parts):
                return parts[position + 1]

        return parts[-1]

    @staticmethod
    def _location(posting):
        if (
            posting.get("jobLocationType")
            == "TELECOMMUTE"
        ):
            return "Remote"

        raw_locations = (
            posting.get("jobLocation")
            or []
        )

        if isinstance(raw_locations, dict):
            raw_locations = [raw_locations]

        locations = []

        for raw_location in raw_locations:
            address = (
                raw_location.get("address")
                or {}
            )

            value = ", ".join(
                str(part)
                for part in (
                    address.get(
                        "addressLocality"
                    ),
                    address.get(
                        "addressRegion"
                    ),
                    address.get(
                        "addressCountry"
                    ),
                )
                if part
            )

            if value and value not in locations:
                locations.append(value)

        return (
            "; ".join(locations)
            or "Not specified"
        )