from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from job_radar.database import (
    GEMINI_BASELINE,
    GEMINI_PENDING,
    GEMINI_QUALIFIED,
    GEMINI_REJECTED,
    JobDatabase,
    make_job_fingerprint,
)
from job_radar.models import Job


def make_job(
    *,
    external_id: str = "job-001",
    company_id: str = "test-company",
    company_name: str = "Test Company",
    title: str = "Junior Data Analyst",
    location: str = "Edmonton, Alberta",
    description: str = (
        "Python, SQL, Excel, and Power BI."
    ),
    job_url: str = (
        "https://example.com/jobs/job-001"
    ),
    source: str = "test",
) -> Job:
    return Job(
        external_id=external_id,
        company_id=company_id,
        company_name=company_name,
        title=title,
        location=location,
        description=description,
        job_url=job_url,
        source=source,
        posted_at=datetime(
            2026,
            9,
            14,
            18,
            0,
            tzinfo=timezone.utc,
        ),
        posted_text="Posted Today",
        employment_type="Full-time",
        workplace_type="Hybrid",
    )


@pytest.fixture
def database(tmp_path) -> JobDatabase:
    database_path = (
        tmp_path / "job_radar.db"
    )

    db = JobDatabase(database_path)
    db.initialize()

    return db


def test_initialize_creates_required_tables(
    database: JobDatabase,
) -> None:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {
        row["name"]
        for row in rows
    }

    assert "jobs" in table_names
    assert "company_state" in table_names
    assert "pipeline_runs" in table_names


def test_initialize_can_run_more_than_once(
    database: JobDatabase,
) -> None:
    database.initialize()
    database.initialize()

    assert database.count_jobs() == 0


def test_database_contains_category_column(
    database: JobDatabase,
) -> None:
    with database.connect() as connection:
        columns = connection.execute(
            "PRAGMA table_info(jobs)"
        ).fetchall()

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

    column_names = {
        column["name"]
        for column in columns
    }

    assert "category" in column_names
    assert version == 2


def test_job_fingerprint_is_stable() -> None:
    first_job = make_job()
    second_job = make_job(
        title=(
            "Updated Junior Data Analyst Title"
        ),
        job_url=(
            "https://example.com/jobs/job-001"
            "?tracking=email"
        ),
    )

    assert make_job_fingerprint(
        first_job
    ) == make_job_fingerprint(second_job)


def test_different_external_ids_have_different_fingerprints(
) -> None:
    first_job = make_job(
        external_id="job-001"
    )
    second_job = make_job(
        external_id="job-002"
    )

    assert make_job_fingerprint(
        first_job
    ) != make_job_fingerprint(second_job)


def test_first_insert_is_new(
    database: JobDatabase,
) -> None:
    job = make_job()

    is_new = database.store_discovered_job(
        job,
        baseline=False,
    )

    assert is_new
    assert database.count_jobs() == 1


def test_second_insert_is_not_new(
    database: JobDatabase,
) -> None:
    job = make_job()

    first_result = (
        database.store_discovered_job(
            job,
            baseline=False,
        )
    )
    second_result = (
        database.store_discovered_job(
            job,
            baseline=False,
        )
    )

    assert first_result
    assert not second_result
    assert database.count_jobs() == 1


def test_existing_job_information_is_refreshed(
    database: JobDatabase,
) -> None:
    first_seen = datetime(
        2026,
        9,
        14,
        18,
        0,
        tzinfo=timezone.utc,
    )
    second_seen = (
        first_seen + timedelta(days=1)
    )

    original_job = make_job(
        description="Original description"
    )
    updated_job = make_job(
        title="Junior Business Data Analyst",
        description="Updated description",
    )

    database.store_discovered_job(
        original_job,
        baseline=False,
        seen_at=first_seen,
    )
    database.store_discovered_job(
        updated_job,
        baseline=False,
        seen_at=second_seen,
    )

    fingerprint = make_job_fingerprint(
        original_job
    )
    stored = database.get_job(fingerprint)

    assert stored is not None
    assert stored["title"] == (
        "Junior Business Data Analyst"
    )
    assert stored["description"] == (
        "Updated description"
    )
    assert stored["first_seen_at"] == (
        first_seen.isoformat()
    )
    assert stored["last_seen_at"] == (
        second_seen.isoformat()
    )


def test_baseline_job_does_not_enter_matching_queue(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=True,
    )

    fingerprint = make_job_fingerprint(
        job
    )
    stored = database.get_job(
        fingerprint
    )

    assert stored is not None
    assert stored["is_baseline"] == 1
    assert stored["gemini_status"] == (
        GEMINI_BASELINE
    )
    assert (
        database.get_jobs_for_matching()
        == []
    )


def test_new_nonbaseline_job_enters_matching_queue(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
    )

    pending_jobs = (
        database.get_jobs_for_matching()
    )

    assert len(pending_jobs) == 1
    assert pending_jobs[0]["gemini_status"] == (
        GEMINI_PENDING
    )
    assert pending_jobs[0]["title"] == (
        "Junior Data Analyst"
    )


def test_company_is_baselined_only_after_success(
    database: JobDatabase,
) -> None:
    company_id = "test-company"

    assert not database.is_company_baselined(
        company_id
    )

    database.record_company_failure(
        company_id,
        "Temporary API failure",
    )

    assert not database.is_company_baselined(
        company_id
    )

    database.record_company_success(
        company_id
    )

    assert database.is_company_baselined(
        company_id
    )


def test_company_baselines_are_independent(
    database: JobDatabase,
) -> None:
    database.record_company_success(
        "company-one"
    )

    assert database.is_company_baselined(
        "company-one"
    )
    assert not database.is_company_baselined(
        "company-two"
    )


def test_company_success_clears_previous_error(
    database: JobDatabase,
) -> None:
    database.record_company_failure(
        "test-company",
        "API unavailable",
    )
    database.record_company_success(
        "test-company"
    )

    state = database.get_company_state(
        "test-company"
    )

    assert state is not None
    assert state["last_error"] is None
    assert state["last_error_at"] is None
    assert state["last_success_at"] is not None


def test_qualified_match_becomes_notification_candidate(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
    )

    fingerprint = make_job_fingerprint(
        job
    )

    database.save_match_result(
        fingerprint,
        score=84.5,
        matched_resume="data-analytics",
        category="data_analytics",
        relevant_skills=[
            "Python",
            "SQL",
            "Power BI",
        ],
        reason=(
            "Strong overlap with analytics "
            "experience."
        ),
        qualified=True,
    )

    candidates = (
        database.get_notification_candidates()
    )

    assert len(candidates) == 1
    assert candidates[0]["gemini_status"] == (
        GEMINI_QUALIFIED
    )
    assert candidates[0]["match_score"] == 84.5
    assert candidates[0]["matched_resume"] == (
        "data-analytics"
    )
    assert candidates[0]["category"] == (
        "data_analytics"
    )
    assert candidates[0]["relevant_skills"] == [
        "Python",
        "SQL",
        "Power BI",
    ]


def test_rejected_match_is_not_notification_candidate(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
    )

    fingerprint = make_job_fingerprint(
        job
    )

    database.save_match_result(
        fingerprint,
        score=42.0,
        matched_resume="data-analytics",
        category="tech_adjacent_other",
        relevant_skills=["Excel"],
        reason="Insufficient role overlap.",
        qualified=False,
    )

    stored = database.get_job(
        fingerprint
    )

    assert stored is not None
    assert stored["gemini_status"] == (
        GEMINI_REJECTED
    )
    assert stored["category"] == (
        "tech_adjacent_other"
    )
    assert (
        database.get_notification_candidates()
        == []
    )


def test_mark_notified_removes_candidate_from_queue(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
    )

    fingerprint = make_job_fingerprint(
        job
    )

    database.save_match_result(
        fingerprint,
        score=90.0,
        matched_resume="software",
        category="software_development",
        relevant_skills=[
            "Python",
            "APIs",
        ],
        reason="Strong software match.",
        qualified=True,
    )

    assert len(
        database.get_notification_candidates()
    ) == 1

    database.mark_notified(fingerprint)

    assert (
        database.get_notification_candidates()
        == []
    )


def test_match_error_can_be_retried(
    database: JobDatabase,
) -> None:
    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
    )

    fingerprint = make_job_fingerprint(
        job
    )

    database.record_match_error(
        fingerprint,
        "Gemini request timed out",
    )

    normal_queue = (
        database.get_jobs_for_matching()
    )
    retry_queue = (
        database.get_jobs_for_matching(
            retry_errors=True
        )
    )

    assert normal_queue == []
    assert len(retry_queue) == 1


def test_cleanup_removes_content_but_keeps_identity(
    database: JobDatabase,
) -> None:
    current_time = datetime(
        2026,
        9,
        14,
        18,
        0,
        tzinfo=timezone.utc,
    )
    old_time = (
        current_time - timedelta(days=31)
    )

    job = make_job()

    database.store_discovered_job(
        job,
        baseline=False,
        seen_at=old_time,
    )

    fingerprint = make_job_fingerprint(
        job
    )

    database.save_match_result(
        fingerprint,
        score=80.0,
        matched_resume="data-analytics",
        category="data_analytics",
        relevant_skills=[
            "Python",
            "SQL",
        ],
        reason="Good analytics match.",
        qualified=True,
        processed_at=old_time,
    )

    cleaned_count = (
        database.cleanup_old_content(
            retention_days=30,
            current_time=current_time,
        )
    )

    stored = database.get_job(
        fingerprint
    )

    assert cleaned_count == 1
    assert stored is not None
    assert stored["description"] is None
    assert stored["relevant_skills"] is None
    assert stored["match_reason"] is None
    assert stored["fingerprint"] == (
        fingerprint
    )
    assert stored["title"] == (
        "Junior Data Analyst"
    )
    assert stored["category"] == (
        "data_analytics"
    )
    assert stored["gemini_status"] == (
        GEMINI_QUALIFIED
    )
    assert database.count_jobs() == 1


def test_pipeline_run_is_recorded(
    database: JobDatabase,
) -> None:
    run_id = database.start_pipeline_run()

    database.complete_pipeline_run(
        run_id,
        successful_companies=16,
        failed_companies=0,
        skipped_companies=25,
        jobs_retrieved=213,
        jobs_prefiltered=58,
        new_jobs=0,
    )

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM pipeline_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    assert row is not None
    assert row["status"] == "completed"
    assert row["successful_companies"] == 16
    assert row["jobs_retrieved"] == 213
    assert row["jobs_prefiltered"] == 58
    assert row["new_jobs"] == 0


def test_unknown_fingerprint_raises_error(
    database: JobDatabase,
) -> None:
    with pytest.raises(KeyError):
        database.mark_notified(
            "fingerprint-that-does-not-exist"
        )