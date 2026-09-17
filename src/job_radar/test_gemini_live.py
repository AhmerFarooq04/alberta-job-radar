from tempfile import TemporaryDirectory
from pathlib import Path

from job_radar.database import (
    JobDatabase,
    make_job_fingerprint,
)
from job_radar.matcher import (
    GeminiMatcher,
    load_resumes,
    process_pending_jobs,
)
from job_radar.models import Job


def main() -> None:
    resumes = load_resumes()

    job = Job(
        external_id="gemini-smoke-test",
        company_id="smoke-test",
        company_name="Smoke Test Company",
        title="Junior Data Analyst",
        location="Edmonton, AB",
        description=(
            "Entry-level data analyst position. "
            "Use Python, SQL, Excel, Power BI, "
            "data visualization, reporting, and "
            "business analysis."
        ),
        job_url=(
            "https://example.com/"
            "gemini-smoke-test"
        ),
        source="smoke-test",
        employment_type="Full-time",
        workplace_type="Hybrid",
    )

    with TemporaryDirectory() as directory:
        database = JobDatabase(
            Path(directory) / "test.db"
        )
        database.initialize()

        database.store_discovered_job(
            job,
            baseline=False,
        )

        matcher = GeminiMatcher()

        try:
            summary = process_pending_jobs(
                database,
                matcher,
                resumes,
                retry_errors=False,
            )
        finally:
            matcher.close()

        fingerprint = make_job_fingerprint(
            job
        )
        stored = database.get_job(
            fingerprint
        )

        print()
        print("GEMINI LIVE TEST")
        print("=" * 50)
        print(f"Queued:   {summary.queued}")
        print(f"Scored:   {summary.succeeded}")
        print(f"Failed:   {summary.failed}")

        if stored is not None:
            print(
                f"Status:   "
                f"{stored['gemini_status']}"
            )
            print(
                f"Score:    "
                f"{stored['match_score']}"
            )
            print(
                f"Category: "
                f"{stored['category']}"
            )
            print(
                f"Resume:   "
                f"{stored['matched_resume']}"
            )
            print(
                f"Skills:   "
                f"{stored['relevant_skills']}"
            )
            print(
                f"Reason:   "
                f"{stored['match_reason']}"
            )

        if summary.succeeded != 1:
            raise SystemExit(
                "Gemini smoke test failed"
            )

        print()
        print("GEMINI SMOKE TEST PASSED")


if __name__ == "__main__":
    main()