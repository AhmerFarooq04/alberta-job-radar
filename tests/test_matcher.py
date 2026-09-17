from pathlib import Path

import pytest

from job_radar.matcher import (
    GeminiMatcher,
    MatchResult,
    build_match_prompt,
    load_resumes,
    process_pending_jobs,
)


class FakeResponse:
    def __init__(
        self,
        text: str | None = None,
        parsed=None,
    ) -> None:
        self.text = text
        self.parsed = parsed


class FakeModels:
    def __init__(
        self,
        responses,
    ) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


class FakeClient:
    def __init__(
        self,
        responses,
    ) -> None:
        self.models = FakeModels(
            responses
        )


class BusyError(RuntimeError):
    code = 503


class FakeDatabase:
    def __init__(
        self,
        jobs,
    ) -> None:
        self.jobs = list(jobs)
        self.saved = []
        self.errors = []

    def get_jobs_for_matching(
        self,
        *,
        retry_errors=False,
        limit=None,
    ):
        jobs = list(self.jobs)

        if limit is not None:
            jobs = jobs[:limit]

        return jobs

    def save_match_result(
        self,
        fingerprint,
        **values,
    ):
        self.saved.append(
            (
                fingerprint,
                values,
            )
        )

    def record_match_error(
        self,
        fingerprint,
        error,
    ):
        self.errors.append(
            (
                fingerprint,
                error,
            )
        )


class FakeMatcher:
    def __init__(
        self,
        results,
    ) -> None:
        self.results = list(results)

    def score_job(
        self,
        job,
        resumes,
    ):
        result = self.results.pop(0)

        if isinstance(result, Exception):
            raise result

        return result


@pytest.fixture
def job() -> dict:
    return {
        "company_name": "Example Company",
        "title": "Junior Data Analyst",
        "location": "Edmonton, AB",
        "employment_type": "Full-time",
        "workplace_type": "Hybrid",
        "description": (
            "Python, SQL and Power BI."
        ),
    }


@pytest.fixture
def resumes() -> dict[str, str]:
    return {
        "data-analytics": (
            "Experience with Python, SQL "
            "and Power BI."
        ),
        "software": (
            "Experience building Python "
            "applications."
        ),
    }


def test_load_resumes(
    tmp_path: Path,
) -> None:
    resume = (
        tmp_path / "data-analytics.md"
    )
    resume.write_text(
        "Python and SQL experience.",
        encoding="utf-8",
    )

    loaded = load_resumes(
        tmp_path
    )

    assert loaded == {
        "data-analytics": (
            "Python and SQL experience."
        )
    }


def test_load_resumes_rejects_empty_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        load_resumes(tmp_path)


def test_prompt_contains_job_and_resumes(
    job,
    resumes,
) -> None:
    prompt = build_match_prompt(
        job,
        resumes,
    )

    assert "Junior Data Analyst" in prompt
    assert "data-analytics" in prompt
    assert "Python" in prompt


def test_matcher_returns_valid_result(
    job,
    resumes,
) -> None:
    response = FakeResponse(
        parsed=MatchResult(
            score=86,
            category="data_analytics",
            matched_resume="data-analytics",
            relevant_skills=[
                "Python",
                "SQL",
                "Power BI",
            ],
            reason=(
                "Strong analytics overlap."
            ),
        )
    )

    client = FakeClient([
        response
    ])

    matcher = GeminiMatcher(
        client=client,
        max_attempts=1,
    )

    result = matcher.score_job(
        job,
        resumes,
    )

    assert result.score == 86
    assert result.category == (
        "data_analytics"
    )
    assert result.matched_resume == (
        "data-analytics"
    )


def test_matcher_parses_json_response(
    job,
    resumes,
) -> None:
    response = FakeResponse(
        text=(
            "{"
            '"score": 72,'
            '"category": "business_analyst",'
            '"matched_resume": '
            '"data-analytics",'
            '"relevant_skills": ["SQL"],'
            '"reason": "Plausible match."'
            "}"
        )
    )

    client = FakeClient([
        response
    ])

    matcher = GeminiMatcher(
        client=client,
        max_attempts=1,
    )

    result = matcher.score_job(
        job,
        resumes,
    )

    assert result.score == 72
    assert result.category == (
        "business_analyst"
    )


def test_matcher_retries_busy_server(
    job,
    resumes,
) -> None:
    valid_response = FakeResponse(
        parsed=MatchResult(
            score=80,
            category="data_analytics",
            matched_resume="data-analytics",
            relevant_skills=[
                "Python",
                "SQL",
            ],
            reason="Good match.",
        )
    )

    client = FakeClient([
        BusyError("Server busy"),
        valid_response,
    ])

    delays = []

    matcher = GeminiMatcher(
        client=client,
        max_attempts=3,
        sleep_function=delays.append,
        random_function=(
            lambda start, end: 0
        ),
    )

    result = matcher.score_job(
        job,
        resumes,
    )

    assert result.score == 80
    assert client.models.calls == 2
    assert delays == [2]


def test_matcher_rejects_unknown_resume(
    job,
    resumes,
) -> None:
    response = FakeResponse(
        parsed=MatchResult(
            score=80,
            category="data_analytics",
            matched_resume=(
                "unknown-resume"
            ),
            relevant_skills=["Python"],
            reason="Good match.",
        )
    )

    client = FakeClient([
        response
    ])

    matcher = GeminiMatcher(
        client=client,
        max_attempts=1,
    )

    with pytest.raises(Exception):
        matcher.score_job(
            job,
            resumes,
        )


def test_process_pending_jobs_saves_category(
) -> None:
    database = FakeDatabase([
        {
            "fingerprint": "job-one",
            "title": (
                "Junior Data Analyst"
            ),
        }
    ])

    matcher = FakeMatcher([
        MatchResult(
            score=82,
            category="data_analytics",
            matched_resume="data-analytics",
            relevant_skills=[
                "Python",
                "SQL",
            ],
            reason="Strong match.",
        )
    ])

    result = process_pending_jobs(
        database,
        matcher,
        {
            "data-analytics": (
                "Python and SQL"
            )
        },
        threshold=75,
    )

    assert result.queued == 1
    assert result.succeeded == 1
    assert result.failed == 0

    fingerprint, saved = (
        database.saved[0]
    )

    assert fingerprint == "job-one"
    assert saved["category"] == (
        "data_analytics"
    )
    assert saved["qualified"] is True


def test_below_threshold_job_is_still_saved(
) -> None:
    database = FakeDatabase([
        {
            "fingerprint": "job-one",
            "title": "Adjacent Role",
        }
    ])

    matcher = FakeMatcher([
        MatchResult(
            score=42,
            category=(
                "tech_adjacent_other"
            ),
            matched_resume="data-analytics",
            relevant_skills=[],
            reason="Weak but possible.",
        )
    ])

    result = process_pending_jobs(
        database,
        matcher,
        {
            "data-analytics": (
                "Python and SQL"
            )
        },
        threshold=75,
    )

    assert result.succeeded == 1
    assert database.saved[0][1][
        "qualified"
    ] is False
    assert database.saved[0][1][
        "score"
    ] == 42


def test_failed_job_does_not_stop_queue(
) -> None:
    database = FakeDatabase([
        {
            "fingerprint": "job-one",
            "title": "First Job",
        },
        {
            "fingerprint": "job-two",
            "title": "Second Job",
        },
    ])

    matcher = FakeMatcher([
        RuntimeError(
            "Gemini unavailable"
        ),
        MatchResult(
            score=70,
            category="business_analyst",
            matched_resume="data-analytics",
            relevant_skills=["Excel"],
            reason="Plausible match.",
        ),
    ])

    result = process_pending_jobs(
        database,
        matcher,
        {
            "data-analytics": "Excel"
        },
        threshold=75,
    )

    assert result.queued == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert len(database.errors) == 1
    assert database.errors[0][0] == (
        "job-one"
    )
    assert database.saved[0][0] == (
        "job-two"
    )


def test_process_pending_jobs_respects_limit(
) -> None:
    database = FakeDatabase([
        {
            "fingerprint": "job-one",
            "title": "First Job",
        },
        {
            "fingerprint": "job-two",
            "title": "Second Job",
        },
    ])

    matcher = FakeMatcher([
        MatchResult(
            score=80,
            category="data_analytics",
            matched_resume="data-analytics",
            relevant_skills=["Python"],
            reason="Good match.",
        )
    ])

    result = process_pending_jobs(
        database,
        matcher,
        {
            "data-analytics": "Python"
        },
        threshold=75,
        limit=1,
    )

    assert result.queued == 1
    assert result.succeeded == 1
    assert len(database.saved) == 1