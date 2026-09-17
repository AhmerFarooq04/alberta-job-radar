from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from job_radar.database import JobDatabase
from job_radar.matcher import (
    GeminiMatcher,
    MatchingRunResult,
    load_resumes,
    process_pending_jobs,
)
from job_radar.pipeline import (
    CompanyRunResult,
    run_pipeline,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape, store and score company jobs."
        )
    )

    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write results to SQLite.",
    )

    parser.add_argument(
        "--match",
        action="store_true",
        help="Score pending jobs using Gemini.",
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/job_radar.db"),
        help="SQLite database path.",
    )

    parser.add_argument(
        "--resumes",
        type=Path,
        default=Path("resumes"),
        help="Resume Markdown directory.",
    )

    parser.add_argument(
        "--match-limit",
        type=int,
        default=None,
        help="Maximum Gemini jobs per run.",
    )

    return parser


def print_company_result(
    result: CompanyRunResult,
    *,
    committed: bool,
) -> None:
    if result.status == "skipped":
        print(
            f"[SKIPPED] {result.company_name} "
            f"({result.ats_type} is not implemented)"
        )
        return

    if result.status == "error":
        print(
            f"[ERROR] {result.company_name}: "
            f"{result.error}"
        )
        return

    matched_count = len(result.matched_jobs)

    status_parts = [
        f"[SUCCESS] {result.company_name}",
        f"retrieved={result.retrieved_count}",
        f"prefiltered={matched_count}",
    ]

    if committed:
        baseline_status = (
            "created"
            if result.baseline_created
            else "existing"
        )

        status_parts.append(
            f"baseline={baseline_status}"
        )
        status_parts.append(
            f"new={len(result.new_jobs)}"
        )

    print(" | ".join(status_parts))

    for job in result.matched_jobs:
        posted_value = (
            job.posted_at
            or job.posted_text
            or "Unknown"
        )

        print()
        print(f"    Title:    {job.title}")
        print(f"    Location: {job.location}")
        print(f"    Posted:   {posted_value}")
        print(
            f"    Type:     "
            f"{job.employment_type}"
        )
        print(f"    URL:      {job.job_url}")

        if committed:
            if result.baseline_created:
                database_status = "baseline"
            elif job in result.new_jobs:
                database_status = "new"
            else:
                database_status = "known"

            print(
                f"    Database: {database_status}"
            )

    if matched_count:
        print()


def main() -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args()

    if arguments.match and not arguments.commit:
        parser.error(
            "--match requires --commit"
        )

    if (
        arguments.match_limit is not None
        and arguments.match_limit < 1
    ):
        parser.error(
            "--match-limit must be at least 1"
        )

    started_at = datetime.now().astimezone()

    heading = (
        "ALBERTA JOB RADAR — DATABASE RUN"
        if arguments.commit
        else "ALBERTA JOB RADAR — DISCOVERY DRY RUN"
    )

    print("=" * 72)
    print(heading)
    print("=" * 72)
    print(f"Started: {started_at.isoformat()}")
    print()

    database: JobDatabase | None = None

    if arguments.commit:
        database = JobDatabase(
            arguments.database
        )

        print("Database writes are enabled.")
        print(
            f"Gemini matching: "
            f"{'enabled' if arguments.match else 'disabled'}"
        )
        print(
            "Notifications are disabled."
        )
        print(
            f"Database: "
            f"{arguments.database.resolve()}"
        )
    else:
        print(
            "No database writes, Gemini calls, "
            "or notifications will occur."
        )

    print()

    result = run_pipeline(
        commit=arguments.commit,
        database=database,
    )

    matching_result: MatchingRunResult | None = None
    cleaned_count = 0

    if database is not None:
        if arguments.match:
            pending_jobs = (
                database.get_jobs_for_matching(
                    retry_errors=True,
                    limit=arguments.match_limit,
                )
            )

            if pending_jobs:
                resumes = load_resumes(
                    arguments.resumes
                )
                matcher = GeminiMatcher()

                try:
                    matching_result = (
                        process_pending_jobs(
                            database,
                            matcher,
                            resumes,
                            retry_errors=True,
                            limit=(
                                arguments.match_limit
                            ),
                        )
                    )
                finally:
                    matcher.close()
            else:
                matching_result = (
                    MatchingRunResult(
                        queued=0,
                        succeeded=0,
                        failed=0,
                    )
                )

        cleaned_count = (
            database.cleanup_old_content(
                retention_days=30
            )
        )

    for company_result in result.company_results:
        print_company_result(
            company_result,
            committed=result.committed,
        )

    print()
    print("=" * 72)
    print("PIPELINE SUMMARY")
    print("=" * 72)
    print(
        f"Successful companies: "
        f"{result.successful_companies}"
    )
    print(
        f"Failed companies:     "
        f"{result.failed_companies}"
    )
    print(
        f"Skipped companies:    "
        f"{result.skipped_companies}"
    )
    print(
        f"Jobs retrieved:       "
        f"{result.total_retrieved}"
    )
    print(
        f"Passed prefilter:      "
        f"{result.total_matched}"
    )

    if result.committed:
        print(
            f"Baselines created:    "
            f"{result.baselines_created}"
        )
        print(
            f"New jobs discovered:  "
            f"{result.total_new}"
        )
        print(
            f"Database run ID:      "
            f"{result.database_run_id}"
        )
        print(
            f"Old content cleaned:  "
            f"{cleaned_count}"
        )

    if matching_result is not None:
        print(
            f"Gemini jobs queued:   "
            f"{matching_result.queued}"
        )
        print(
            f"Gemini jobs scored:   "
            f"{matching_result.succeeded}"
        )
        print(
            f"Gemini jobs failed:   "
            f"{matching_result.failed}"
        )

    print()

    if result.committed:
        print("DATABASE RUN COMPLETE")
    else:
        print("DRY RUN COMPLETE")


if __name__ == "__main__":
    main()