from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from job_radar.database import JobDatabase, datetime_to_text


Category = Literal[
    "data_analytics",
    "software_development",
    "it_systems",
    "business_analyst",
    "tech_adjacent_other",
]

Period = Literal["today", "week", "month"]

CATEGORIES = {
    "data_analytics": "Data & Analytics",
    "software_development": "Software Development",
    "it_systems": "IT & Systems Systems",
    "business_analyst": "Business / General Analyst",
    "tech_adjacent_other": "Tech-Adjacent / Other",
}

LOCAL_TIMEZONE = ZoneInfo("America/Edmonton")


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category | None


def period_start(
    period: Period,
    now: datetime,
) -> datetime:
    if period == "today":
        return now.astimezone(LOCAL_TIMEZONE).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ).astimezone(timezone.utc)

    days = 7 if period == "week" else 30
    return now.astimezone(timezone.utc) - timedelta(days=days)


JOB_SELECT = """
    SELECT
        j.fingerprint,
        j.company_id,
        j.company_name,
        j.title,
        j.location,
        j.job_url,
        j.posted_at,
        j.posted_text,
        j.first_seen_at,
        j.last_seen_at,
        j.employment_type,
        j.workplace_type,
        j.is_baseline,
        j.gemini_status,
        j.match_score,
        j.matched_resume,
        j.relevant_skills,
        CASE
            WHEN j.gemini_status IN ('qualified', 'rejected')
            THEN j.match_reason
            ELSE NULL
        END AS match_reason,
        j.category AS gemini_category,
        o.category AS category_override,
        COALESCE(
            o.category,
            j.category,
            'tech_adjacent_other'
        ) AS category
    FROM jobs AS j
    LEFT JOIN job_category_overrides AS o
        ON o.fingerprint = j.fingerprint
"""


def serialize_job(row) -> dict:
    job = dict(row)
    job["is_baseline"] = bool(job["is_baseline"])
    job["relevant_skills"] = json.loads(
        job["relevant_skills"] or "[]"
    )
    return job


def create_app(
    database_path: str | Path | None = None,
    *,
    clock=None,
) -> FastAPI:
    load_dotenv()
    database = JobDatabase(
        database_path
        if database_path is not None
        else os.getenv("JOB_RADAR_DATABASE", "data/job_radar.db")
    )
    current_time = clock or (
        lambda: datetime.now(timezone.utc)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()

        with database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_category_overrides (
                    fingerprint TEXT PRIMARY KEY
                        REFERENCES jobs(fingerprint) ON DELETE CASCADE,
                    category TEXT NOT NULL CHECK (
                        category IN (
                            'data_analytics',
                            'software_development',
                            'it_systems',
                            'business_analyst',
                            'tech_adjacent_other'
                        )
                    ),
                    updated_at TEXT NOT NULL
                )
                """
            )

        yield

    app = FastAPI(
        title="Alberta Job Radar",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["GET", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health():
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.get("/api/jobs")
    def list_jobs(
        period: Period = "today",
        include_baseline: bool = False,
    ):
        now = current_time()
        start = period_start(period, now)

        sql = JOB_SELECT + """
            WHERE j.first_seen_at >= ?
                AND j.first_seen_at <= ?
        """

        parameters = [
            datetime_to_text(start),
            datetime_to_text(now),
        ]

        if not include_baseline:
            sql += " AND j.is_baseline = 0"

        sql += """
            ORDER BY
                j.match_score IS NULL,
                j.match_score DESC,
                j.first_seen_at DESC,
                j.fingerprint ASC
        """

        with database.connect() as connection:
            rows = connection.execute(
                sql,
                parameters,
            ).fetchall()

        jobs = [serialize_job(row) for row in rows]

        return {
            "period": period,
            "timezone": "America/Edmonton",
            "from": datetime_to_text(start),
            "to": datetime_to_text(now),
            "total": len(jobs),
            "categories": CATEGORIES,
            "jobs": jobs,
        }

    @app.patch("/api/jobs/{fingerprint}")
    def update_category(
        fingerprint: str,
        update: CategoryUpdate,
    ):
        with database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM jobs WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()

            if exists is None:
                raise HTTPException(
                    status_code=404,
                    detail="Job not found",
                )

            if update.category is None:
                connection.execute(
                    """
                    DELETE FROM job_category_overrides
                    WHERE fingerprint = ?
                    """,
                    (fingerprint,),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO job_category_overrides (
                        fingerprint,
                        category,
                        updated_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        category = excluded.category,
                        updated_at = excluded.updated_at
                    """,
                    (
                        fingerprint,
                        update.category,
                        datetime_to_text(current_time()),
                    ),
                )

            row = connection.execute(
                JOB_SELECT + " WHERE j.fingerprint = ?",
                (fingerprint,),
            ).fetchone()

        return serialize_job(row)

    return app


app = create_app()