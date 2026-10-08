"""Conservative posting-date parsing and calendar-month retention."""
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("America/Edmonton")


def parse_posted_date(value, *, reference=None):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        pass
    text = re.sub(r"^posted\s+", "", value.lower())
    ref = reference or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    day = ref.astimezone(LOCAL).date()
    if text == "today":
        return datetime.combine(day, datetime.min.time())
    if text == "yesterday":
        return datetime.combine(day - timedelta(days=1), datetime.min.time())
    match = re.fullmatch(r"(\d+) days? ago", text)
    if match:
        return datetime.combine(day - timedelta(days=int(match[1])), datetime.min.time())
    # Rounded weeks/months and '30+ days' are bounds, not exact posting dates.
    return None


def posting_date_text(value):
    if value is None:
        return None
    if value.tzinfo is None and value.time() == datetime.min.time():
        return value.date().isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def two_month_cutoff(now):
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = now.astimezone(LOCAL).date()
    month_index = day.year * 12 + day.month - 1 - 2
    year, month = divmod(month_index, 12)
    return day.replace(year=year, month=month + 1,
                       day=min(day.day, monthrange(year, month + 1)[1]))


def is_expired(*, posted_at=None, posted_text=None, first_seen_at=None, last_seen_at=None, now=None):
    now = now or datetime.now(timezone.utc)
    reference = parse_posted_date(last_seen_at) if isinstance(last_seen_at, str) else last_seen_at
    value = parse_posted_date(posted_at) if isinstance(posted_at, str) else posted_at
    if value is not None:
        value_day = value.astimezone(LOCAL).date() if value.tzinfo else value.date()
        today = now.astimezone(LOCAL).date() if now.tzinfo else now.date()
        if value_day > today:
            value = None
    if value is None:
        value = parse_posted_date(posted_text, reference=reference or now)
    if value is None:
        # A lower-bound age can establish expiry without inventing an exact date.
        match = re.fullmatch(r"(?:posted\s+)?(\d+)\+ days? ago", (posted_text or "").lower().strip())
        if match:
            ref = reference or now
            value = ref - timedelta(days=int(match[1]))
    if value is None:
        value = parse_posted_date(first_seen_at) if isinstance(first_seen_at, str) else first_seen_at
    if value is None:
        return False
    day = value.astimezone(LOCAL).date() if value.tzinfo else value.date()
    return day <= two_month_cutoff(now)



def extract_html_posted_date(soup):
    """Use only job posting metadata or explicitly labelled dates."""
    import json
    def visit(value):
        if isinstance(value, list):
            for item in value:
                found = visit(item)
                if found:
                    return found
        elif isinstance(value, dict):
            kind = value.get("@type", [])
            if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
                found = parse_posted_date(value.get("datePosted"))
                if found:
                    return found
            return visit(value.get("@graph", []))
        return None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            found = visit(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
        if found:
            return found
    for element in soup.select('[itemprop="datePosted"], time[data-posted], meta[name="datePosted"]'):
        found = parse_posted_date(element.get("datetime") or element.get("content") or element.get_text(strip=True))
        if found:
            return found
    match = re.search(r"(?:date posted|posted on|posting date)\s*[:?]?\s*(\d{4}-\d{2}-\d{2}|[A-Za-z]+ \d{1,2},? \d{4})", soup.get_text(" ", strip=True), re.I)
    return parse_posted_date(match[1]) if match else None
