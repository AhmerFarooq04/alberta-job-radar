from datetime import datetime, timezone

from job_radar.scrapers.workable import (
    WorkableScraper,
    markdown_to_text,
)


def make_company(**overrides):
    company = {
        "id": "blackline-safety",
        "name": "Blackline Safety",
        "ats": {
            "type": "workable",
            "account": "blacklinesafety",
        },
        "prefilter_enabled": False,
    }

    company.update(overrides)

    return company


class FakeResponse:
    def __init__(
        self,
        payload=None,
        text="",
    ):
        self.payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.get_urls = []

    def post(
        self,
        url,
        json,
        timeout,
    ):
        return FakeResponse({
            "total": 1,
            "results": [{
                "shortcode": "ABC123",
                "title": "Data Analyst",
                "published": (
                    "2026-09-15T00:00:00Z"
                ),
                "type": "full",
                "workplace": "hybrid",
                "remote": False,
                "location": {
                    "city": "Calgary",
                    "region": "Alberta",
                    "country": "Canada",
                },
            }],
        })

    def get(
        self,
        url,
        timeout,
    ):
        self.get_urls.append(url)

        return FakeResponse(
            text=(
                "# Data Analyst\n\n"
                "## Description\n\n"
                "Analyze **data**."
            )
        )


def test_workable_job(
    monkeypatch,
):
    session = FakeSession()

    monkeypatch.setattr(
        (
            "job_radar.scrapers.workable"
            ".requests.Session"
        ),
        lambda: session,
    )

    job = WorkableScraper(
        make_company()
    ).fetch_jobs()[0]

    assert job.external_id == "ABC123"
    assert job.title == "Data Analyst"
    assert job.location == (
        "Calgary, Alberta, Canada"
    )
    assert "Analyze data." in job.description
    assert job.posted_at == datetime(
        2026,
        9,
        15,
        tzinfo=timezone.utc,
    )
    assert job.workplace_type == "Hybrid"
    assert job.source == "workable"


def test_markdown_to_text():
    value = (
        "# Title\n\n"
        "- Analyze **data**\n"
        "- Build [reports](https://example.com)"
    )

    result = markdown_to_text(value)

    assert "Analyze data" in result
    assert "Build reports" in result
    assert "**" not in result