from datetime import datetime

from job_radar.scrapers.jsonld import (
    JsonLdScraper,
    parse_date,
)


def make_company(**overrides):
    company = {
        "id": "test-company",
        "name": "Test Company",
        "careers_url": (
            "https://example.com/jobs"
        ),
        "ats": {
            "type": "jsonld",
            "listing_url": (
                "https://example.com/jobs"
            ),
            "link_pattern": (
                "example[.]com/jobs/[0-9]+"
            ),
        },
        "prefilter_enabled": False,
    }

    company.update(overrides)

    return company


class FakeResponse:
    def __init__(
        self,
        text,
        url,
    ):
        self.text = text
        self.url = url

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.headers = {}

    def get(
        self,
        url,
        timeout,
    ):
        if url.endswith("/jobs"):
            return FakeResponse(
                (
                    '<a href="/jobs/123">'
                    "Data Analyst"
                    "</a>"
                ),
                url,
            )

        return FakeResponse(
            """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Data Analyst",
  "description": "<p>Analyze data.</p>",
  "datePosted": "2026-09-15",
  "employmentType": "FULL_TIME",
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Edmonton",
      "addressRegion": "AB",
      "addressCountry": "CA"
    }
  },
  "url": "https://example.com/jobs/123"
}
</script>
""",
            url,
        )


def test_jsonld_job(
    monkeypatch,
):
    monkeypatch.setattr(
        (
            "job_radar.scrapers.jsonld"
            ".requests.Session"
        ),
        FakeSession,
    )

    jobs = JsonLdScraper(
        make_company()
    ).fetch_jobs()

    assert len(jobs) == 1

    job = jobs[0]

    assert job.external_id == "123"
    assert job.title == "Data Analyst"
    assert (
        job.location
        == "Edmonton, AB, CA"
    )
    assert job.description == "Analyze data."
    assert (
        job.employment_type
        == "FULL_TIME"
    )
    assert job.source == "jsonld"


def test_jsonld_date():
    assert parse_date(
        "2026-09-15"
    ) == datetime(
        2026,
        9,
        15,
    )