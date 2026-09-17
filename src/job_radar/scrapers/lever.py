from datetime import datetime, timezone

import requests

from job_radar.models import Job
from job_radar.scrapers.base import (
    BaseScraper,
    html_to_text,
)


class LeverScraper(BaseScraper):
    API_URL = (
        "https://api.lever.co/v0/postings/{site}"
    )

    def fetch_jobs(self) -> list[Job]:
        site = self.company["ats"]["site"]

        response = requests.get(
            self.API_URL.format(site=site),
            params={"mode": "json"},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; AlbertaJobRadar/0.1)"
                )
            },
            timeout=30,
        )

        response.raise_for_status()

        postings = response.json()

        if not isinstance(postings, list):
            raise ValueError(
                f"Lever returned invalid job data for "
                f"{self.company['name']}"
            )

        return [
            self._convert_posting(posting)
            for posting in postings
        ]

    def _build_description(
        self,
        posting: dict,
    ) -> str:
        """
        Combine all Lever description sections.

        Lever often places responsibilities and qualifications inside
        `lists` rather than `descriptionPlain`.
        """

        parts = []

        description = posting.get(
            "descriptionPlain",
            "",
        )

        if description.strip():
            parts.append(description.strip())

        for section in posting.get("lists", []):
            heading = section.get("text", "")
            content = html_to_text(
                section.get("content", "")
            )

            section_parts = []

            if heading.strip():
                section_parts.append(heading.strip())

            if content.strip():
                section_parts.append(content.strip())

            if section_parts:
                parts.append(
                    "\n".join(section_parts)
                )

        additional = (
            posting.get("additionalPlain")
            or html_to_text(
                posting.get("additional", "")
            )
        )

        if additional.strip():
            parts.append(additional.strip())

        return "\n\n".join(parts)

    def _convert_posting(
        self,
        posting: dict,
    ) -> Job:
        categories = posting.get("categories") or {}
        created_timestamp = posting.get("createdAt")

        posted_at = None

        if created_timestamp:
            posted_at = datetime.fromtimestamp(
                created_timestamp / 1000,
                tz=timezone.utc,
            )

        return Job(
            external_id=str(posting["id"]),
            company_id=self.company["id"],
            company_name=self.company["name"],
            title=posting.get(
                "text",
                "Unknown title",
            ),
            location=categories.get(
                "location",
                "Not specified",
            ),
            description=self._build_description(
                posting
            ),
            job_url=posting.get("hostedUrl", ""),
            source="lever",
            posted_at=posted_at,
            employment_type=categories.get(
                "commitment"
            ),
            workplace_type=posting.get(
                "workplaceType"
            ),
        )