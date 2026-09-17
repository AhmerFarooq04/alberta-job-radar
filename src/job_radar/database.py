from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from contextlib import contextmanager

from job_radar.models import Job


GEMINI_BASELINE = "baseline"
GEMINI_PENDING = "pending"
GEMINI_QUALIFIED = "qualified"
GEMINI_REJECTED = "rejected"
GEMINI_ERROR = "error"

VALID_GEMINI_STATUSES = (
    GEMINI_BASELINE,
    GEMINI_PENDING,
    GEMINI_QUALIFIED,
    GEMINI_REJECTED,
    GEMINI_ERROR,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def datetime_to_text(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    ).isoformat()


def normalize_identity_value(
    value: str | None,
) -> str:
    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value.strip().lower(),
    )


def canonicalize_url(
    url: str | None,
) -> str:
    if not url:
        return ""

    parsed = urlsplit(url.strip())

    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def make_job_fingerprint(
    job: Job,
) -> str:
    company_id = normalize_identity_value(
        job.company_id
    )
    external_id = normalize_identity_value(
        job.external_id
    )
    canonical_url = canonicalize_url(
        job.job_url
    )

    if external_id:
        identity = (
            f"{company_id}|external-id|"
            f"{external_id}"
        )
    elif canonical_url:
        identity = (
            f"{company_id}|url|"
            f"{canonical_url}"
        )
    else:
        title = normalize_identity_value(
            job.title
        )
        location = normalize_identity_value(
            job.location
        )
        identity = (
            f"{company_id}|fallback|"
            f"{title}|{location}"
        )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


class JobDatabase:
    def __init__(
        self,
        database_path: str | Path = (
            "data/job_radar.db"
        ),
    ) -> None:
        self.database_path = Path(
            database_path
        )

    @contextmanager
    def connect(self):
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )

        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")

            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    fingerprint TEXT PRIMARY KEY,

                    external_id TEXT,
                    company_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,

                    title TEXT NOT NULL,
                    location TEXT,
                    description TEXT,
                    job_url TEXT NOT NULL,
                    source TEXT NOT NULL,

                    posted_at TEXT,
                    posted_text TEXT,
                    employment_type TEXT,
                    workplace_type TEXT,

                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_baseline INTEGER NOT NULL DEFAULT 0,

                    gemini_status TEXT NOT NULL,
                    match_score REAL,
                    matched_resume TEXT,
                    category TEXT,
                    relevant_skills TEXT,
                    match_reason TEXT,
                    gemini_processed_at TEXT,

                    notified_at TEXT,

                    CHECK (is_baseline IN (0, 1)),
                    CHECK (
                        gemini_status IN (
                            'baseline',
                            'pending',
                            'qualified',
                            'rejected',
                            'error'
                        )
                    )
                );

                CREATE TABLE IF NOT EXISTS company_state (
                    company_id TEXT PRIMARY KEY,
                    baseline_completed_at TEXT,
                    last_success_at TEXT,
                    last_error_at TEXT,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,

                    successful_companies INTEGER
                        NOT NULL DEFAULT 0,
                    failed_companies INTEGER
                        NOT NULL DEFAULT 0,
                    skipped_companies INTEGER
                        NOT NULL DEFAULT 0,

                    jobs_retrieved INTEGER
                        NOT NULL DEFAULT 0,
                    jobs_prefiltered INTEGER
                        NOT NULL DEFAULT 0,
                    new_jobs INTEGER
                        NOT NULL DEFAULT 0,

                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS
                    idx_jobs_company
                ON jobs (company_id);

                CREATE INDEX IF NOT EXISTS
                    idx_jobs_gemini_status
                ON jobs (gemini_status);

                CREATE INDEX IF NOT EXISTS
                    idx_jobs_last_seen
                ON jobs (last_seen_at);

                CREATE INDEX IF NOT EXISTS
                    idx_jobs_notified
                ON jobs (notified_at);


                """
            )

            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(jobs)"
                ).fetchall()
            }

            if "category" not in columns:
                connection.execute(
                    """
                    ALTER TABLE jobs
                    ADD COLUMN category TEXT
                    """
                )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_jobs_category
                ON jobs (category)
                """
            )

            connection.execute(
                "PRAGMA user_version = 2"
            )

    def is_company_baselined(
        self,
        company_id: str,
    ) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT baseline_completed_at
                FROM company_state
                WHERE company_id = ?
                """,
                (company_id,),
            ).fetchone()

        return bool(
            row
            and row["baseline_completed_at"]
        )

    def record_company_success(
        self,
        company_id: str,
        completed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            completed_at or utc_now()
        )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO company_state (
                    company_id,
                    baseline_completed_at,
                    last_success_at,
                    last_error_at,
                    last_error
                )
                VALUES (?, ?, ?, NULL, NULL)

                ON CONFLICT(company_id) DO UPDATE SET
                    baseline_completed_at = COALESCE(
                        company_state.baseline_completed_at,
                        excluded.baseline_completed_at
                    ),
                    last_success_at =
                        excluded.last_success_at,
                    last_error_at = NULL,
                    last_error = NULL
                """,
                (
                    company_id,
                    timestamp,
                    timestamp,
                ),
            )

    def record_company_failure(
        self,
        company_id: str,
        error: str,
        failed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            failed_at or utc_now()
        )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO company_state (
                    company_id,
                    baseline_completed_at,
                    last_success_at,
                    last_error_at,
                    last_error
                )
                VALUES (?, NULL, NULL, ?, ?)

                ON CONFLICT(company_id) DO UPDATE SET
                    last_error_at =
                        excluded.last_error_at,
                    last_error =
                        excluded.last_error
                """,
                (
                    company_id,
                    timestamp,
                    error,
                ),
            )

    def get_company_state(
        self,
        company_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM company_state
                WHERE company_id = ?
                """,
                (company_id,),
            ).fetchone()

        if row is None:
            return None

        return dict(row)

    def store_discovered_job(
        self,
        job: Job,
        *,
        baseline: bool,
        seen_at: datetime | None = None,
    ) -> bool:
        timestamp = datetime_to_text(
            seen_at or utc_now()
        )
        posted_at = datetime_to_text(
            job.posted_at
        )
        fingerprint = make_job_fingerprint(
            job
        )

        gemini_status = (
            GEMINI_BASELINE
            if baseline
            else GEMINI_PENDING
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    fingerprint,
                    external_id,
                    company_id,
                    company_name,
                    title,
                    location,
                    description,
                    job_url,
                    source,
                    posted_at,
                    posted_text,
                    employment_type,
                    workplace_type,
                    first_seen_at,
                    last_seen_at,
                    is_baseline,
                    gemini_status
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    fingerprint,
                    job.external_id,
                    job.company_id,
                    job.company_name,
                    job.title,
                    job.location,
                    job.description,
                    job.job_url,
                    job.source,
                    posted_at,
                    job.posted_text,
                    job.employment_type,
                    job.workplace_type,
                    timestamp,
                    timestamp,
                    int(baseline),
                    gemini_status,
                ),
            )

            is_new = cursor.rowcount == 1

            if not is_new:
                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        company_name = ?,
                        title = ?,
                        location = ?,
                        description = CASE
                            WHEN ? IS NOT NULL
                                AND ? != ''
                            THEN ?
                            ELSE description
                        END,
                        job_url = ?,
                        source = ?,
                        posted_at = COALESCE(
                            ?,
                            posted_at
                        ),
                        posted_text = COALESCE(
                            ?,
                            posted_text
                        ),
                        employment_type = COALESCE(
                            ?,
                            employment_type
                        ),
                        workplace_type = COALESCE(
                            ?,
                            workplace_type
                        ),
                        last_seen_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        job.company_name,
                        job.title,
                        job.location,
                        job.description,
                        job.description,
                        job.description,
                        job.job_url,
                        job.source,
                        posted_at,
                        job.posted_text,
                        job.employment_type,
                        job.workplace_type,
                        timestamp,
                        fingerprint,
                    ),
                )

        return is_new

    def get_job(
        self,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)

        if result["relevant_skills"]:
            result["relevant_skills"] = (
                json.loads(
                    result["relevant_skills"]
                )
            )

        return result

    def get_jobs_for_matching(
        self,
        *,
        retry_errors: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        statuses = [GEMINI_PENDING]

        if retry_errors:
            statuses.append(GEMINI_ERROR)

        placeholders = ", ".join(
            "?" for _ in statuses
        )

        sql = f"""
            SELECT *
            FROM jobs
            WHERE gemini_status IN ({placeholders})
            ORDER BY first_seen_at ASC
        """

        parameters: list[Any] = list(statuses)

        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)

        with self.connect() as connection:
            rows = connection.execute(
                sql,
                parameters,
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    def save_match_result(
        self,
        fingerprint: str,
        *,
        score: float,
        matched_resume: str,
        relevant_skills: list[str],
        reason: str,
        qualified: bool,
        category: str | None = None,
        processed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            processed_at or utc_now()
        )

        status = (
            GEMINI_QUALIFIED
            if qualified
            else GEMINI_REJECTED
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    gemini_status = ?,
                    match_score = ?,
                    matched_resume = ?,
                    category = ?,
                    relevant_skills = ?,
                    match_reason = ?,
                    gemini_processed_at = ?
                WHERE fingerprint = ?
                """,
                (
                    status,
                    score,
                    matched_resume,
                    category,
                    json.dumps(
                        relevant_skills
                    ),
                    reason,
                    timestamp,
                    fingerprint,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(
                    "Unknown job fingerprint: "
                    f"{fingerprint}"
                )

    def record_match_error(
        self,
        fingerprint: str,
        error: str,
        processed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            processed_at or utc_now()
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    gemini_status = ?,
                    match_reason = ?,
                    gemini_processed_at = ?
                WHERE fingerprint = ?
                """,
                (
                    GEMINI_ERROR,
                    error,
                    timestamp,
                    fingerprint,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(
                    "Unknown job fingerprint: "
                    f"{fingerprint}"
                )

    def get_notification_candidates(
        self,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE
                    gemini_status = ?
                    AND notified_at IS NULL
                ORDER BY
                    match_score DESC,
                    first_seen_at ASC
                """,
                (GEMINI_QUALIFIED,),
            ).fetchall()

        results = []

        for row in rows:
            result = dict(row)

            if result["relevant_skills"]:
                result["relevant_skills"] = (
                    json.loads(
                        result[
                            "relevant_skills"
                        ]
                    )
                )

            results.append(result)

        return results

    def mark_notified(
        self,
        fingerprint: str,
        notified_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            notified_at or utc_now()
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET notified_at = ?
                WHERE fingerprint = ?
                """,
                (
                    timestamp,
                    fingerprint,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(
                    "Unknown job fingerprint: "
                    f"{fingerprint}"
                )

    def cleanup_old_content(
        self,
        *,
        retention_days: int = 30,
        current_time: datetime | None = None,
    ) -> int:
        now = current_time or utc_now()
        cutoff = now - timedelta(
            days=retention_days
        )
        cutoff_text = datetime_to_text(
            cutoff
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    description = NULL,
                    relevant_skills = NULL,
                    match_reason = NULL
                WHERE
                    last_seen_at < ?
                    AND (
                        description IS NOT NULL
                        OR relevant_skills IS NOT NULL
                        OR match_reason IS NOT NULL
                    )
                """,
                (cutoff_text,),
            )

            return cursor.rowcount

    def delete_expired_fingerprints(
        self,
        *,
        retention_days: int = 365,
        current_time: datetime | None = None,
    ) -> int:
        now = current_time or utc_now()
        cutoff = now - timedelta(
            days=retention_days
        )
        cutoff_text = datetime_to_text(
            cutoff
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM jobs
                WHERE last_seen_at < ?
                """,
                (cutoff_text,),
            )

            return cursor.rowcount

    def start_pipeline_run(
        self,
        started_at: datetime | None = None,
    ) -> int:
        timestamp = datetime_to_text(
            started_at or utc_now()
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs (
                    started_at,
                    status
                )
                VALUES (?, 'running')
                """,
                (timestamp,),
            )

            return int(cursor.lastrowid)

    def complete_pipeline_run(
        self,
        run_id: int,
        *,
        successful_companies: int,
        failed_companies: int,
        skipped_companies: int,
        jobs_retrieved: int,
        jobs_prefiltered: int,
        new_jobs: int,
        completed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            completed_at or utc_now()
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pipeline_runs
                SET
                    completed_at = ?,
                    status = 'completed',
                    successful_companies = ?,
                    failed_companies = ?,
                    skipped_companies = ?,
                    jobs_retrieved = ?,
                    jobs_prefiltered = ?,
                    new_jobs = ?,
                    error_message = NULL
                WHERE id = ?
                """,
                (
                    timestamp,
                    successful_companies,
                    failed_companies,
                    skipped_companies,
                    jobs_retrieved,
                    jobs_prefiltered,
                    new_jobs,
                    run_id,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(
                    f"Unknown pipeline run: {run_id}"
                )

    def fail_pipeline_run(
        self,
        run_id: int,
        error: str,
        completed_at: datetime | None = None,
    ) -> None:
        timestamp = datetime_to_text(
            completed_at or utc_now()
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pipeline_runs
                SET
                    completed_at = ?,
                    status = 'failed',
                    error_message = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    error,
                    run_id,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(
                    f"Unknown pipeline run: {run_id}"
                )

    def count_jobs(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM jobs
                """
            ).fetchone()

        return int(row["total"])