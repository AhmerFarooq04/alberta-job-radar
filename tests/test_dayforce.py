from datetime import datetime, timezone

import pytest

from job_radar.scrapers.dayforce import (
    DayforceScraper,
    parse_date,
)


def make_company(**overrides):
    company = {
        "id": "alberta-innovates",
        "name": "Alberta Innovates",
        "ats": {
            "type": "dayforce",
            "namespace": "innovates",
            "board": "AlbertaInnovates",
        },
        "prefilter_enabled": False,
    }

    company.update(overrides)

    return company


class FakeResponse:
    def __init__(
        self,
        payload,
        error=None,
    ):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(
        self,
        pages,
    ):
        self.pages = list(pages)
        self.headers = {}
        self.post_calls = []

    def get(
        self,
        url,
        timeout,
    ):
        return FakeResponse({
            "csrfToken": "token",
        })

    def post(
        self,
        url,
        json,
        headers,
        timeout,
    ):
        self.post_calls.append({
            "url": url,
            "json": json,
            "headers": headers,
        })

        return FakeResponse(
            self.pages.pop(0)
        )


def sample_posting(
    job_id="101",
    title="Junior Data Analyst",
):
    return {
        "jobPostingId": job_id,
        "jobTitle": title,
        "jobDescription": (
            "<p>Analyze research data.</p>"
        ),
        "postingStartTimestampUTC": (
            "2026-09-15T15:30:00Z"
        ),
        "postingLocations": [{
            "formattedAddress": (
                "Edmonton, AB, CAN"
            ),
        }],
        "employmentType": "Full Time",
        "hasVirtualLocation": False,
    }


def install_session(
    monkeypatch,
    pages,
):
    session = FakeSession(pages)

    monkeypatch.setattr(
        (
            "job_radar.scrapers.dayforce"
            ".requests.Session"
        ),
        lambda: session,
    )

    return session


def test_normalizes_dayforce_job(
    monkeypatch,
):
    session = install_session(
        monkeypatch,
        [{
            "maxCount": 1,
            "jobPostings": [
                sample_posting()
            ],
        }],
    )

    job = DayforceScraper(
        make_company()
    ).fetch_jobs()[0]

    assert job.external_id == "101"
    assert (
        job.title
        == "Junior Data Analyst"
    )
    assert (
        job.location
        == "Edmonton, AB, CAN"
    )
    assert (
        job.description
        == "Analyze research data."
    )
    assert job.posted_at == datetime(
        2026,
        9,
        15,
        15,
        30,
        tzinfo=timezone.utc,
    )
    assert job.source == "dayforce"

    assert (
        session.post_calls[0]
        ["headers"]
        ["X-CSRF-TOKEN"]
        == "token"
    )


def test_dayforce_paginates(
    monkeypatch,
):
    first = sample_posting("101")
    second = sample_posting(
        "102",
        "Business Analyst",
    )

    install_session(
        monkeypatch,
        [
            {
                "maxCount": 2,
                "jobPostings": [first],
            },
            {
                "maxCount": 2,
                "jobPostings": [second],
            },
        ],
    )

    jobs = DayforceScraper(
        make_company()
    ).fetch_jobs()

    assert [
        job.external_id
        for job in jobs
    ] == [
        "101",
        "102",
    ]


def test_dayforce_remote_location(
    monkeypatch,
):
    posting = sample_posting()
    posting[
        "hasVirtualLocation"
    ] = True

    install_session(
        monkeypatch,
        [{
            "maxCount": 1,
            "jobPostings": [posting],
        }],
    )

    job = DayforceScraper(
        make_company()
    ).fetch_jobs()[0]

    assert (
        job.location
        == "Remote — Edmonton, AB, CAN"
    )
    assert (
        job.workplace_type
        == "Remote"
    )


def test_parse_date():
    assert parse_date(
        "2026-09-15T15:30:00Z"
    ) == datetime(
        2026,
        9,
        15,
        15,
        30,
        tzinfo=timezone.utc,
    )

    assert parse_date(None) is None
    assert parse_date("invalid") is None