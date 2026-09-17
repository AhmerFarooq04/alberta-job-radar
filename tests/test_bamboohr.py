from datetime import datetime

import pytest

from job_radar.scrapers.bamboohr import (
    BambooHRScraper,
    parse_posted_date,
)
from job_radar.scrapers import create_scraper


def make_company(**overrides) -> dict:
    company = {
        "id": "yardstick-technologies",
        "name": "Yardstick Technologies",
        "ats": {
            "type": "bamboohr",
            "subdomain": "yardsticktechnologies",
        },
        "prefilter_enabled": False,
        "detail_delay_seconds": 0,
    }
    company.update(overrides)
    return company


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload

        return self.payload


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.requested_urls = []
        self.headers = {}

    def get(self, url: str, timeout: int):
        self.requested_urls.append(url)
        return self.responses[url]


def install_fake_session(
    monkeypatch,
    responses: dict[str, FakeResponse],
) -> FakeSession:
    session = FakeSession(responses)
    monkeypatch.setattr(
        "job_radar.scrapers.bamboohr.requests.Session",
        lambda: session,
    )
    return session


def test_fetch_jobs_normalizes_bamboohr_job(monkeypatch) -> None:
    base_url = (
        "https://yardsticktechnologies.bamboohr.com/careers"
    )
    summary = {
        "id": "64",
        "jobOpeningName": "Service Desk Analyst - Tier 1",
        "employmentStatusLabel": "Full-Time",
        "location": {
            "city": "Edmonton",
            "state": "Alberta",
        },
    }
    detail = {
        "result": {
            "jobOpening": {
                **summary,
                "datePosted": "2026-08-22",
                "description": (
                    "<p>Support Windows devices.</p>"
                    "<ul><li>Resolve tickets</li></ul>"
                ),
                "jobOpeningShareUrl": f"{base_url}/64",
                "jobOpeningStatus": "Open",
            }
        }
    }

    session = install_fake_session(
        monkeypatch,
        {
            f"{base_url}/list": FakeResponse(
                {"meta": {"totalCount": 1}, "result": [summary]}
            ),
            f"{base_url}/64/detail": FakeResponse(detail),
        },
    )

    jobs = BambooHRScraper(make_company()).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "64"
    assert job.title == "Service Desk Analyst - Tier 1"
    assert job.location == "Edmonton, Alberta"
    assert job.description == (
        "Support Windows devices. Resolve tickets"
    )
    assert job.job_url == f"{base_url}/64"
    assert job.source == "bamboohr"
    assert job.posted_at == datetime(2026, 8, 22)
    assert job.employment_type == "Full-Time"
    assert session.requested_urls == [
        f"{base_url}/list",
        f"{base_url}/64/detail",
    ]


def test_remote_location_is_labelled(monkeypatch) -> None:
    base_url = "https://samsters.bamboohr.com/careers"
    summary = {
        "id": "12",
        "jobOpeningName": "Data Analyst",
        "isRemote": True,
        "location": {
            "addressCountry": "Canada",
        },
    }

    install_fake_session(
        monkeypatch,
        {
            f"{base_url}/list": FakeResponse(
                {"result": [summary]}
            ),
            f"{base_url}/12/detail": FakeResponse(
                {
                    "result": {
                        "jobOpening": {
                            **summary,
                            "description": "<p>Analyze data.</p>",
                        }
                    }
                }
            ),
        },
    )

    company = make_company(
        id="samdesk",
        name="samdesk",
        ats={
            "type": "bamboohr",
            "subdomain": "samsters",
        },
    )
    job = BambooHRScraper(company).fetch_jobs()[0]

    assert job.location == "Remote — Canada"
    assert job.workplace_type == "Remote"


def test_prefilter_runs_before_detail_requests(
    monkeypatch,
) -> None:
    base_url = (
        "https://yardsticktechnologies.bamboohr.com/careers"
    )
    summary = {
        "id": "99",
        "jobOpeningName": "Account Executive",
        "location": {
            "city": "Edmonton",
            "state": "Alberta",
        },
    }
    session = install_fake_session(
        monkeypatch,
        {
            f"{base_url}/list": FakeResponse(
                {"result": [summary]}
            )
        },
    )
    monkeypatch.setattr(
        "job_radar.scrapers.bamboohr.passes_prefilter_values",
        lambda **kwargs: False,
    )

    company = make_company(prefilter_enabled=True)
    jobs = BambooHRScraper(company).fetch_jobs()

    assert jobs == []
    assert session.requested_urls == [
        f"{base_url}/list"
    ]


def test_invalid_summary_payload_raises(monkeypatch) -> None:
    base_url = (
        "https://yardsticktechnologies.bamboohr.com/careers"
    )
    install_fake_session(
        monkeypatch,
        {
            f"{base_url}/list": FakeResponse(
                {"result": {"id": "wrong-shape"}}
            )
        },
    )

    with pytest.raises(
        ValueError,
        match="invalid job summaries",
    ):
        BambooHRScraper(make_company()).fetch_jobs()


def test_parse_posted_date_handles_bad_values() -> None:
    assert parse_posted_date(None) is None
    assert parse_posted_date("not-a-date") is None


def test_factory_creates_bamboohr_scraper() -> None:
    scraper = create_scraper(make_company())

    assert isinstance(scraper, BambooHRScraper)
