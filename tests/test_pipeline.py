from __future__ import annotations

from pathlib import Path

from job_radar.database import JobDatabase
from job_radar.models import Job
from job_radar.pipeline import (
    filter_jobs,
    run_pipeline,
)


def make_job(
    title: str,
    location: str,
    employment_type: str | None = None,
    *,
    external_id: str | None = None,
) -> Job:
    resolved_external_id = (
        external_id
        if external_id is not None
        else title
    )

    return Job(
        external_id=resolved_external_id,
        company_id="test-company",
        company_name="Test Company",
        title=title,
        location=location,
        description="Example description",
        job_url=(
            "https://example.com/jobs/"
            f"{resolved_external_id}"
        ),
        source="test",
        employment_type=employment_type,
    )


def make_company(
    *,
    company_id: str = "test-company",
    ats_type: str = "lever",
) -> dict:
    return {
        "id": company_id,
        "name": "Test Company",
        "enabled": True,
        "include_internships": False,
        "target_locations": [
            "Alberta",
            "Ontario",
            "Remote Canada",
        ],
        "ats": {
            "type": ats_type,
            "board": "test-board",
        },
    }


class FakeScraper:
    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.jobs = jobs or []
        self.error = error

    def fetch_jobs(self) -> list[Job]:
        if self.error is not None:
            raise self.error

        return self.jobs


def create_test_database(
    tmp_path: Path,
) -> JobDatabase:
    database = JobDatabase(
        tmp_path / "job_radar.db"
    )
    database.initialize()

    return database


def test_filter_jobs_accepts_target_job() -> None:
    jobs = [
        make_job(
            title="Junior Data Analyst",
            location="Edmonton, AB",
        )
    ]

    matched_jobs = filter_jobs(jobs)

    assert len(matched_jobs) == 1


def test_filter_jobs_rejects_wrong_location() -> None:
    jobs = [
        make_job(
            title="Junior Data Analyst",
            location="New York, NY, USA",
        )
    ]

    matched_jobs = filter_jobs(jobs)

    assert matched_jobs == []


def test_filter_jobs_rejects_wrong_role() -> None:
    jobs = [
        make_job(
            title="Petroleum Terminal Operator",
            location="Calgary, AB",
        )
    ]

    matched_jobs = filter_jobs(jobs)

    assert matched_jobs == []


def test_filter_jobs_rejects_senior_role() -> None:
    jobs = [
        make_job(
            title="Senior Data Analyst",
            location="Toronto, ON",
        )
    ]

    matched_jobs = filter_jobs(jobs)

    assert matched_jobs == []


def test_filter_jobs_rejects_internship() -> None:
    jobs = [
        make_job(
            title="Data Analyst Intern",
            location="Edmonton, AB",
            employment_type="Intern",
        )
    ]

    matched_jobs = filter_jobs(jobs)

    assert matched_jobs == []


def test_filter_jobs_can_include_internship() -> None:
    jobs = [
        make_job(
            title="Data Analyst Intern",
            location="Edmonton, AB",
            employment_type="Intern",
        )
    ]

    matched_jobs = filter_jobs(
        jobs,
        include_internships=True,
    )

    assert len(matched_jobs) == 1


def test_filter_jobs_handles_mixed_list() -> None:
    jobs = [
        make_job(
            "Junior Business Analyst",
            "Calgary, AB",
        ),
        make_job(
            "Senior Business Analyst",
            "Calgary, AB",
        ),
        make_job(
            "Petroleum Terminal Operator",
            "Edmonton, AB",
        ),
        make_job(
            "Software Developer I",
            "Toronto, ON",
        ),
        make_job(
            "Data Analyst",
            "Seattle, WA, USA",
        ),
    ]

    matched_jobs = filter_jobs(jobs)

    matched_titles = [
        job.title
        for job in matched_jobs
    ]

    assert matched_titles == [
        "Junior Business Analyst",
        "Software Developer I",
    ]


def test_dry_run_does_not_write_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    job = make_job(
        "Junior Data Analyst",
        "Edmonton, AB",
    )

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper([job]),
    )

    result = run_pipeline(
        commit=False,
        database=database,
    )

    assert result.committed is False
    assert result.total_matched == 1
    assert result.total_new == 0
    assert database.count_jobs() == 0
    assert not database.is_company_baselined(
        "test-company"
    )


def test_first_committed_run_creates_baseline(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    job = make_job(
        "Junior Data Analyst",
        "Edmonton, AB",
    )

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper([job]),
    )

    result = run_pipeline(
        commit=True,
        database=database,
    )

    assert result.committed is True
    assert result.baselines_created == 1
    assert result.total_new == 0

    assert database.count_jobs() == 1
    assert database.is_company_baselined(
        "test-company"
    )

    assert (
        database.get_jobs_for_matching()
        == []
    )


def test_second_run_does_not_repeat_existing_job(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    job = make_job(
        "Junior Data Analyst",
        "Edmonton, AB",
    )

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper([job]),
    )

    first_result = run_pipeline(
        commit=True,
        database=database,
    )
    second_result = run_pipeline(
        commit=True,
        database=database,
    )

    assert first_result.baselines_created == 1
    assert first_result.total_new == 0

    assert second_result.baselines_created == 0
    assert second_result.total_new == 0

    assert database.count_jobs() == 1
    assert (
        database.get_jobs_for_matching()
        == []
    )


def test_new_job_after_baseline_enters_matching_queue(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    original_job = make_job(
        "Junior Data Analyst",
        "Edmonton, AB",
        external_id="job-001",
    )
    new_job = make_job(
        "Business Systems Analyst",
        "Calgary, AB",
        external_id="job-002",
    )

    current_jobs = [original_job]

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper(
            list(current_jobs)
        ),
    )

    baseline_result = run_pipeline(
        commit=True,
        database=database,
    )

    current_jobs.append(new_job)

    second_result = run_pipeline(
        commit=True,
        database=database,
    )

    assert baseline_result.total_new == 0
    assert second_result.total_new == 1

    assert second_result.company_results[
        0
    ].new_jobs == [new_job]

    pending_jobs = (
        database.get_jobs_for_matching()
    )

    assert len(pending_jobs) == 1
    assert pending_jobs[0]["external_id"] == (
        "job-002"
    )


def test_failed_company_is_not_baselined(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper(
            error=RuntimeError(
                "Temporary source failure"
            )
        ),
    )

    result = run_pipeline(
        commit=True,
        database=database,
    )

    assert result.failed_companies == 1
    assert result.baselines_created == 0
    assert not database.is_company_baselined(
        "test-company"
    )

    state = database.get_company_state(
        "test-company"
    )

    assert state is not None
    assert "Temporary source failure" in (
        state["last_error"]
    )


def test_skipped_company_is_not_baselined(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [
            make_company(
                ats_type="generic"
            )
        ],
    )

    result = run_pipeline(
        commit=True,
        database=database,
    )

    assert result.skipped_companies == 1
    assert result.baselines_created == 0
    assert not database.is_company_baselined(
        "test-company"
    )


def test_pipeline_run_is_written_to_audit_table(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = create_test_database(tmp_path)

    job = make_job(
        "Junior Data Analyst",
        "Edmonton, AB",
    )

    monkeypatch.setattr(
        "job_radar.pipeline.load_companies",
        lambda: [make_company()],
    )
    monkeypatch.setattr(
        "job_radar.pipeline.create_scraper",
        lambda company: FakeScraper([job]),
    )

    result = run_pipeline(
        commit=True,
        database=database,
    )

    assert result.database_run_id is not None

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM pipeline_runs
            WHERE id = ?
            """,
            (
                result.database_run_id,
            ),
        ).fetchone()

    assert row is not None
    assert row["status"] == "completed"
    assert row["successful_companies"] == 1
    assert row["jobs_retrieved"] == 1
    assert row["jobs_prefiltered"] == 1
    assert row["new_jobs"] == 0