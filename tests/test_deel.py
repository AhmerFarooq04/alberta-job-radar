import json

from job_radar.scrapers.deel import DeelScraper


def make_company():
    return {
        "id": "carbon-upcycling",
        "name": "Carbon Upcycling",
        "careers_url": (
            "https://example.com/careers"
        ),
        "ats": {
            "type": "deel",
            "slug": (
                "carbon-upcycling-technologies"
            ),
        },
        "prefilter_enabled": False,
    }


SUMMARY = {
    "id": "job-posting-id",
    "title": "Data Analyst",
    "createdAt": (
        "2026-09-15T00:00:00Z"
    ),
    "job": {
        "workArrangementEnum": "HYBRID",
        "jobEmploymentTypes": [{
            "employmentType": {
                "name": "Full-time",
            },
        }],
        "jobLocations": [{
            "location": {
                "name": "Calgary, AB",
            },
        }],
    },
}


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
        if "job-details" in url:
            return FakeResponse(
                """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Data Analyst",
  "description": "<p>Analyze carbon data.</p>",
  "datePosted": "2026-09-15",
  "employmentType": "Full-time"
}
</script>
""",
                url,
            )

        stream = (
            '"jobPostings":'
            + json.dumps([SUMMARY])
            + ',"orgSlug":"carbon"'
        )

        script_data = json.dumps(
            [1, stream]
        )

        return FakeResponse(
            (
                "<script>"
                "self.__next_f.push("
                f"{script_data}"
                ")"
                "</script>"
            ),
            url,
        )


def test_deel_job(
    monkeypatch,
):
    monkeypatch.setattr(
        (
            "job_radar.scrapers.deel"
            ".requests.Session"
        ),
        FakeSession,
    )

    job = DeelScraper(
        make_company()
    ).fetch_jobs()[0]

    assert (
        job.external_id
        == "job-posting-id"
    )
    assert job.title == "Data Analyst"
    assert job.location == "Calgary, AB"
    assert (
        job.description
        == "Analyze carbon data."
    )
    assert (
        job.employment_type
        == "Full-time"
    )
    assert (
        job.workplace_type
        == "Hybrid"
    )
    assert job.source == "deel"