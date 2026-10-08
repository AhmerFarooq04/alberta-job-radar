from datetime import datetime, timezone
from bs4 import BeautifulSoup
from job_radar.dates import parse_posted_date, posting_date_text, is_expired, two_month_cutoff, extract_html_posted_date
from job_radar.database import JobDatabase, make_job_fingerprint
from job_radar.models import Job

NOW = datetime(2026, 10, 7, 18, tzinfo=timezone.utc)


def test_formats_and_invalid_values():
    for value in ("2026-09-15", "September 15, 2026", "Sep 15, 2026", "09/15/2026"):
        assert parse_posted_date(value).date().isoformat() == "2026-09-15"
    assert parse_posted_date("2026-09-15T10:00:00-06:00").utcoffset().total_seconds() == -21600
    for value in (None, 123, "invalid", "2026-02-30", "30+ days ago", "2 months ago"):
        assert parse_posted_date(value) is None


def test_relative_dates_use_edmonton_calendar_day():
    reference = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)
    assert posting_date_text(parse_posted_date("Posted Today", reference=reference)) == "2026-10-07"
    assert posting_date_text(parse_posted_date("Posted Yesterday", reference=reference)) == "2026-10-06"
    assert posting_date_text(parse_posted_date("Posted 7 Days Ago", reference=reference)) == "2026-09-30"


def test_calendar_month_expiry_and_unknown_fallback():
    assert two_month_cutoff(NOW).isoformat() == "2026-08-07"
    assert two_month_cutoff(datetime(2026, 4, 30, 18, tzinfo=timezone.utc)).isoformat() == "2026-02-28"
    assert is_expired(posted_at="2026-08-07", first_seen_at=NOW, now=NOW)
    assert not is_expired(posted_at="2026-08-08", now=NOW)
    assert is_expired(posted_at="invalid", first_seen_at="2026-07-01", now=NOW)
    assert is_expired(posted_text="Posted 90+ Days Ago", last_seen_at=NOW, now=NOW)
    assert not is_expired(posted_text="Posted 30+ Days Ago", first_seen_at=NOW, now=NOW)
    assert is_expired(posted_text="Posted Yesterday", last_seen_at="2026-08-01T18:00:00Z", now=NOW)


def test_html_job_metadata_does_not_use_page_update_date():
    soup = BeautifulSoup('<script type="application/ld+json">{"@graph":[{"@type":"WebPage","dateModified":"2026-10-07"},{"@type":"JobPosting","datePosted":"2026-09-15"}]}</script>', 'html.parser')
    assert posting_date_text(extract_html_posted_date(soup)) == "2026-09-15"
    assert extract_html_posted_date(BeautifulSoup('<time>2026-10-07</time>', 'html.parser')) is None


def make_job(posted=None, text=None):
    return Job(external_id="one", company_id="test", company_name="Test",
               title="Data Analyst", location="Edmonton", description="Python SQL",
               job_url="https://example.com/one", source="test", posted_at=posted, posted_text=text)


def test_storage_skips_old_jobs_and_keeps_date_only(tmp_path):
    db = JobDatabase(tmp_path / "jobs.db")
    db.initialize()
    old = make_job(datetime(2026, 8, 7))
    assert not db.store_discovered_job(old, baseline=False, seen_at=NOW)
    assert db.get_job(make_job_fingerprint(old)) is None
    recent = make_job(datetime(2026, 9, 15))
    assert db.store_discovered_job(recent, baseline=False, seen_at=NOW)
    assert db.get_job(make_job_fingerprint(recent))["posted_at"] == "2026-09-15"


def test_deletion_uses_posting_age_even_if_recently_scraped(tmp_path):
    db = JobDatabase(tmp_path / "jobs.db")
    db.initialize()
    job = make_job(datetime(2026, 8, 1))
    db.store_discovered_job(job, baseline=True, seen_at=datetime(2026, 8, 2, 18, tzinfo=timezone.utc))
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET last_seen_at = ?", (NOW.isoformat(),))
    assert db.delete_old_jobs(current_time=NOW) == 1
    assert db.get_job(make_job_fingerprint(job)) is None
    assert db.delete_old_jobs(current_time=NOW) == 0


def test_relative_date_does_not_drift_on_repeat_scrapes(tmp_path):
    db = JobDatabase(tmp_path / "jobs.db")
    db.initialize()
    job = make_job(text="Posted 30 Days Ago")
    db.store_discovered_job(job, baseline=False, seen_at=NOW)
    db.store_discovered_job(job, baseline=False, seen_at=datetime(2026, 10, 8, 18, tzinfo=timezone.utc))
    assert db.get_job(make_job_fingerprint(job))["posted_at"] == "2026-09-07"
