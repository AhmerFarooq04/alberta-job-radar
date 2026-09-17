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
from job_radar.notifications.telegram import (
    NotificationResult,
    TelegramNotifier,
    notify_pending_jobs,
)
from job_radar.pipeline import CompanyRunResult, run_pipeline


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape, store, score and notify company jobs."
    )
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--match", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument(
        "--database", type=Path, default=Path("data/job_radar.db")
    )
    parser.add_argument(
        "--resumes", type=Path, default=Path("resumes")
    )
    parser.add_argument("--match-limit", type=int, default=None)
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
        print(f"[ERROR] {result.company_name}: {result.error}")
        return

    parts = [
        f"[SUCCESS] {result.company_name}",
        f"retrieved={result.retrieved_count}",
        f"prefiltered={len(result.matched_jobs)}",
    ]
    if committed:
        baseline = "created" if result.baseline_created else "existing"
        parts.extend([
            f"baseline={baseline}",
            f"new={len(result.new_jobs)}",
        ])
    print(" | ".join(parts))

    for job in result.matched_jobs:
        print()
        print(f"    Title:    {job.title}")
        print(f"    Location: {job.location}")
        print(f"    Posted:   {job.posted_at or job.posted_text or 'Unknown'}")
        print(f"    Type:     {job.employment_type}")
        print(f"    URL:      {job.job_url}")
        if committed:
            state = (
                "baseline" if result.baseline_created
                else "new" if job in result.new_jobs
                else "known"
            )
            print(f"    Database: {state}")


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if (args.match or args.notify) and not args.commit:
        parser.error("--match and --notify require --commit")

    if args.match_limit is not None and args.match_limit < 1:
        parser.error("--match-limit must be at least 1")

    print("=" * 72)
    print(
        "ALBERTA JOB RADAR — DATABASE RUN"
        if args.commit
        else "ALBERTA JOB RADAR — DISCOVERY DRY RUN"
    )
    print(f"Started: {datetime.now().astimezone().isoformat()}")

    if args.commit:
        print(f"Database: {args.database.resolve()}")
        print(f"Gemini: {'enabled' if args.match else 'disabled'}")
        print(f"Telegram: {'enabled' if args.notify else 'disabled'}")
    else:
        print("No database writes, Gemini calls, or notifications.")

    database = JobDatabase(args.database) if args.commit else None
    result = run_pipeline(commit=args.commit, database=database)

    for company_result in result.company_results:
        print_company_result(company_result, committed=result.committed)

    matching = MatchingRunResult(queued=0, succeeded=0, failed=0)
    notifications = NotificationResult()
    stage_failed = False
    cleaned_count = 0

    if database is not None:
        if args.match:
            try:
                pending = database.get_jobs_for_matching(
                    retry_errors=True,
                    limit=args.match_limit,
                )
                if pending:
                    resumes = load_resumes(args.resumes)
                    matcher = GeminiMatcher()
                    try:
                        matching = process_pending_jobs(
                            database,
                            matcher,
                            resumes,
                            retry_errors=True,
                            limit=args.match_limit,
                        )
                    finally:
                        matcher.close()
            except Exception as error:
                stage_failed = True
                print(f"[MATCH STAGE ERROR] {type(error).__name__}")

        if args.notify:
            try:
                notifier = TelegramNotifier()
                try:
                    notifications = notify_pending_jobs(database, notifier)
                finally:
                    notifier.close()
            except Exception as error:
                stage_failed = True
                print(f"[NOTIFICATION STAGE ERROR] {type(error).__name__}")

        # Preserve content while jobs are waiting for scoring or retry.
        if not database.get_jobs_for_matching(retry_errors=True, limit=1):
            cleaned_count = database.cleanup_old_content(retention_days=30)

    print()
    print("=" * 72)
    print("PIPELINE SUMMARY")
    print("=" * 72)
    print(f"Successful companies: {result.successful_companies}")
    print(f"Failed companies:     {result.failed_companies}")
    print(f"Skipped companies:    {result.skipped_companies}")
    print(f"Jobs retrieved:       {result.total_retrieved}")
    print(f"Passed prefilter:     {result.total_matched}")

    if result.committed:
        print(f"Baselines created:    {result.baselines_created}")
        print(f"New jobs discovered:  {result.total_new}")
        print(f"Database run ID:      {result.database_run_id}")
        print(f"Old content cleaned:  {cleaned_count}")

    if args.match:
        print(f"Gemini jobs queued:   {matching.queued}")
        print(f"Gemini jobs scored:   {matching.succeeded}")
        print(f"Gemini jobs failed:   {matching.failed}")

    if args.notify:
        print(f"Telegram queued:      {notifications.queued}")
        print(f"Telegram sent:        {notifications.sent}")
        print(f"Telegram failed:      {notifications.failed}")

    failed = (
        stage_failed
        or result.failed_companies > 0
        or matching.failed > 0
        or notifications.failed > 0
    )
    print("RUN FINISHED WITH ERRORS" if failed else "RUN COMPLETE")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()