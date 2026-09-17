from __future__ import annotations

from dataclasses import dataclass, field

from job_radar.config import load_companies
from job_radar.database import JobDatabase
from job_radar.filters import passes_prefilter
from job_radar.models import Job
from job_radar.scrapers import (
    SUPPORTED_ATS_TYPES,
    create_scraper,
)


@dataclass
class CompanyRunResult:
    company_id: str
    company_name: str
    ats_type: str
    status: str

    retrieved_count: int = 0
    matched_jobs: list[Job] = field(
        default_factory=list
    )
    new_jobs: list[Job] = field(
        default_factory=list
    )

    baseline_created: bool = False
    error: str | None = None


@dataclass
class PipelineRunResult:
    company_results: list[CompanyRunResult]
    committed: bool = False
    database_run_id: int | None = None

    @property
    def successful_companies(self) -> int:
        return sum(
            result.status == "success"
            for result in self.company_results
        )

    @property
    def failed_companies(self) -> int:
        return sum(
            result.status == "error"
            for result in self.company_results
        )

    @property
    def skipped_companies(self) -> int:
        return sum(
            result.status == "skipped"
            for result in self.company_results
        )

    @property
    def total_retrieved(self) -> int:
        return sum(
            result.retrieved_count
            for result in self.company_results
        )

    @property
    def total_matched(self) -> int:
        return sum(
            len(result.matched_jobs)
            for result in self.company_results
        )

    @property
    def total_new(self) -> int:
        """
        Count newly discovered non-baseline jobs.

        Baseline jobs are intentionally not included.
        """
        return sum(
            len(result.new_jobs)
            for result in self.company_results
        )

    @property
    def baselines_created(self) -> int:
        return sum(
            result.baseline_created
            for result in self.company_results
        )


def filter_jobs(
    jobs: list[Job],
    include_internships: bool = False,
) -> list[Job]:
    """
    Apply the inexpensive prefilter to normalized jobs.
    """
    return [
        job
        for job in jobs
        if passes_prefilter(
            job,
            include_internships=include_internships,
        )
    ]


def persist_company_jobs(
    database: JobDatabase,
    *,
    company_id: str,
    jobs: list[Job],
) -> tuple[bool, list[Job]]:
    """
    Store one company's successfully retrieved jobs.

    Returns:
        A tuple containing:

        1. Whether this was the company's baseline run.
        2. Newly discovered non-baseline jobs.

    A company is marked as baselined only after every filtered job has been
    stored successfully.
    """
    was_already_baselined = (
        database.is_company_baselined(company_id)
    )
    is_baseline_run = not was_already_baselined

    new_jobs: list[Job] = []

    for job in jobs:
        was_inserted = database.store_discovered_job(
            job,
            baseline=is_baseline_run,
        )

        if was_inserted and not is_baseline_run:
            new_jobs.append(job)

    database.record_company_success(company_id)

    return is_baseline_run, new_jobs


def run_pipeline(
    *,
    commit: bool = False,
    database: JobDatabase | None = None,
) -> PipelineRunResult:
    """
    Run scraping and prefiltering.

    Dry-run mode:
        run_pipeline()

        No database writes occur.

    Commit mode:
        run_pipeline(commit=True)

        Jobs are stored in SQLite. Each company's first successful run becomes
        that company's baseline. Only later discoveries are considered new.

    This stage does not call Gemini or send notifications.
    """
    active_database: JobDatabase | None = None
    database_run_id: int | None = None

    if commit:
        active_database = (
            database
            if database is not None
            else JobDatabase()
        )
        active_database.initialize()
        database_run_id = (
            active_database.start_pipeline_run()
        )

    company_results: list[CompanyRunResult] = []

    try:
        companies = load_companies()

        for company in companies:
            company_id = company["id"]
            company_name = company["name"]
            ats_type = company["ats"]["type"]

            if ats_type not in SUPPORTED_ATS_TYPES:
                company_results.append(
                    CompanyRunResult(
                        company_id=company_id,
                        company_name=company_name,
                        ats_type=ats_type,
                        status="skipped",
                    )
                )
                continue

            try:
                scraper = create_scraper(company)
                retrieved_jobs = scraper.fetch_jobs()

                include_internships = company.get(
                    "include_internships",
                    False,
                )

                matched_jobs = filter_jobs(
                    retrieved_jobs,
                    include_internships=(
                        include_internships
                    ),
                )

                baseline_created = False
                new_jobs: list[Job] = []

                if active_database is not None:
                    (
                        baseline_created,
                        new_jobs,
                    ) = persist_company_jobs(
                        active_database,
                        company_id=company_id,
                        jobs=matched_jobs,
                    )

                company_results.append(
                    CompanyRunResult(
                        company_id=company_id,
                        company_name=company_name,
                        ats_type=ats_type,
                        status="success",
                        retrieved_count=len(
                            retrieved_jobs
                        ),
                        matched_jobs=matched_jobs,
                        new_jobs=new_jobs,
                        baseline_created=(
                            baseline_created
                        ),
                    )
                )

            except Exception as error:
                error_message = (
                    f"{type(error).__name__}: {error}"
                )

                if active_database is not None:
                    active_database.record_company_failure(
                        company_id,
                        error_message,
                    )

                company_results.append(
                    CompanyRunResult(
                        company_id=company_id,
                        company_name=company_name,
                        ats_type=ats_type,
                        status="error",
                        error=error_message,
                    )
                )

        result = PipelineRunResult(
            company_results=company_results,
            committed=commit,
            database_run_id=database_run_id,
        )

        if (
            active_database is not None
            and database_run_id is not None
        ):
            active_database.complete_pipeline_run(
                database_run_id,
                successful_companies=(
                    result.successful_companies
                ),
                failed_companies=(
                    result.failed_companies
                ),
                skipped_companies=(
                    result.skipped_companies
                ),
                jobs_retrieved=result.total_retrieved,
                jobs_prefiltered=result.total_matched,
                new_jobs=result.total_new,
            )

        return result

    except Exception as error:
        if (
            active_database is not None
            and database_run_id is not None
        ):
            active_database.fail_pipeline_run(
                database_run_id,
                (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        raise