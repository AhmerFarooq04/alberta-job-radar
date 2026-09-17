from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from job_radar.api import create_app
from job_radar.database import JobDatabase, make_job_fingerprint
from job_radar.models import Job


NOW = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    database = JobDatabase(tmp_path / "test.db")
    app = create_app(
        database.database_path,
        clock=lambda: NOW,
    )

    with TestClient(app) as client:
        yield client, database


def add_job(
    database,
    external_id,
    *,
    seen_at=NOW,
    baseline=False,
    score=None,
):
    job = Job(
        external_id=external_id,
        company_id="test-company",
        company_name="Test Company",
        title="Data Analyst",
        location="Edmonton, AB",
        description="SQL and Excel reporting.",
        job_url=f"https://example.com/jobs/{external_id}",
        source="test",
    )

    database.store_discovered_job(
        job,
        baseline=baseline,
        seen_at=seen_at,
    )

    fingerprint = make_job_fingerprint(job)

    if score is not None:
        database.save_match_result(
            fingerprint,
            score=score,
            category="data_analytics",
            matched_resume="data-analytics",
            relevant_skills=["SQL"],
            reason="Relevant reporting experience.",
            qualified=score >= 75,
        )

    return fingerprint


def test_health(setup):
    client, _ = setup
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_baselines_hidden_by_default(setup):
    client, database = setup
    add_job(database, "baseline", baseline=True)
    add_job(database, "new")

    response = client.get("/api/jobs")
    assert response.json()["total"] == 1

    response = client.get(
        "/api/jobs?include_baseline=true"
    )
    assert response.json()["total"] == 2


def test_all_scores_and_errors_remain_visible(setup):
    client, database = setup

    high = add_job(database, "high", score=95)
    low = add_job(database, "low", score=20)
    pending = add_job(database, "pending")
    failed = add_job(database, "failed")

    database.record_match_error(
        failed,
        "Internal provider error details",
    )

    jobs = client.get("/api/jobs").json()["jobs"]
    by_id = {job["fingerprint"]: job for job in jobs}

    assert len(jobs) == 4
    assert jobs[0]["fingerprint"] == high
    assert jobs[1]["fingerprint"] == low
    assert by_id[pending]["match_score"] is None
    assert by_id[failed]["gemini_status"] == "error"
    assert by_id[failed]["match_reason"] is None
    assert by_id[pending]["category"] == "tech_adjacent_other"


def test_today_uses_edmonton_midnight(setup):
    client, database = setup

    add_job(
        database,
        "before-midnight",
        seen_at=datetime(
            2026, 9, 16, 5, 59, tzinfo=timezone.utc
        ),
    )
    included = add_job(
        database,
        "at-midnight",
        seen_at=datetime(
            2026, 9, 16, 6, 0, tzinfo=timezone.utc
        ),
    )

    jobs = client.get("/api/jobs?period=today").json()["jobs"]

    assert len(jobs) == 1
    assert jobs[0]["fingerprint"] == included


def test_week_and_month_filters(setup):
    client, database = setup

    add_job(database, "today")
    add_job(database, "six-days", seen_at=NOW - timedelta(days=6))
    add_job(database, "eight-days", seen_at=NOW - timedelta(days=8))
    add_job(database, "old", seen_at=NOW - timedelta(days=31))

    assert client.get(
        "/api/jobs?period=week"
    ).json()["total"] == 2

    assert client.get(
        "/api/jobs?period=month"
    ).json()["total"] == 3


def test_manual_category_survives_new_gemini_score(setup):
    client, database = setup
    fingerprint = add_job(database, "job", score=80)

    response = client.patch(
        f"/api/jobs/{fingerprint}",
        json={"category": "business_analyst"},
    )

    assert response.status_code == 200
    assert response.json()["category"] == "business_analyst"

    database.save_match_result(
        fingerprint,
        score=90,
        category="software_development",
        matched_resume="software",
        relevant_skills=["Python"],
        reason="Updated assessment.",
        qualified=True,
    )

    job = client.get("/api/jobs").json()["jobs"][0]

    assert job["category"] == "business_analyst"
    assert job["gemini_category"] == "software_development"

    response = client.patch(
        f"/api/jobs/{fingerprint}",
        json={"category": None},
    )

    assert response.json()["category"] == "software_development"
    assert response.json()["category_override"] is None


def test_category_override_persists_after_restart(setup):
    client, database = setup
    fingerprint = add_job(database, "job")

    client.patch(
        f"/api/jobs/{fingerprint}",
        json={"category": "it_systems"},
    )

    other_app = create_app(
        database.database_path,
        clock=lambda: NOW,
    )

    with TestClient(other_app) as other_client:
        jobs = other_client.get("/api/jobs").json()["jobs"]

    assert jobs[0]["category"] == "it_systems"


def test_invalid_requests(setup):
    client, database = setup
    fingerprint = add_job(database, "job")

    assert client.get(
        "/api/jobs?period=year"
    ).status_code == 422

    assert client.patch(
        f"/api/jobs/{fingerprint}",
        json={"category": "invalid"},
    ).status_code == 422

    assert client.patch(
        "/api/jobs/missing",
        json={"category": "it_systems"},
    ).status_code == 404