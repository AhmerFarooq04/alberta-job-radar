import requests

from job_radar.filters import passes_prefilter_values
from job_radar.models import Job
from job_radar.scrapers.base import BaseScraper, html_to_text


class CollageScraper(BaseScraper):
    def __init__(self, company):
        super().__init__(company)

        self.site = company["ats"]["site"]

        self.endpoint = (
            "https://api.collage.co/v1/"
            f"positions/{self.site}"
        )

    def fetch_jobs(self):
        response = requests.get(
            self.endpoint,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()

        postings = response.json().get(
            "positions",
            [],
        )

        if not isinstance(postings, list):
            raise ValueError(
                f"Invalid Collage response: "
                f"{self.company['name']}"
            )

        jobs = []

        for posting in postings:
            title = posting.get(
                "title",
                "Unknown title",
            )
            location = (
                posting.get("location")
                or "Not specified"
            )
            employment_type = posting.get(
                "employmentType"
            )

            if self.company.get(
                "prefilter_enabled",
                True,
            ):
                if not passes_prefilter_values(
                    title=title,
                    location=location,
                    employment_type=employment_type,
                    include_internships=self.company.get(
                        "include_internships",
                        False,
                    ),
                ):
                    continue

            url = (
                posting.get("hostedUrl")
                or self.company["careers_url"]
            )

            job_id = str(
                posting.get("id")
                or url.rstrip("/").split("/")[-1]
            )

            jobs.append(
                Job(
                    external_id=job_id,
                    company_id=self.company["id"],
                    company_name=self.company["name"],
                    title=title,
                    location=location,
                    description=html_to_text(
                        posting.get(
                            "description",
                            "",
                        )
                    ),
                    job_url=url,
                    source="collage",
                    employment_type=employment_type,
                    workplace_type=posting.get(
                        "workplaceType"
                    ),
                )
            )

        return jobs