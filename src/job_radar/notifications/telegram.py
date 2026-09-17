from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from html import escape
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

from job_radar.database import JobDatabase


@dataclass
class NotificationResult:
    queued: int = 0
    sent: int = 0
    failed: int = 0


class TelegramNotifier:
    def __init__(self) -> None:
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not token or not self.chat_id:
            raise ValueError(
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )

        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.session = requests.Session()

    def send(self, text: str) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }

        for attempt in range(3):
            delay = 2 ** (attempt + 1)

            try:
                response = self.session.post(
                    self.url,
                    json=payload,
                    timeout=(10, 30),
                )
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError(
                        "Telegram network request failed; delivery uncertain."
                    ) from None
            else:
                try:
                    body = response.json()
                except ValueError:
                    body = {}

                if response.ok and body.get("ok"):
                    return

                code = body.get("error_code", response.status_code)

                if code not in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"Telegram rejected request: {code}")

                retry_after = body.get("parameters", {}).get("retry_after")
                if retry_after is not None:
                    delay = max(delay, float(retry_after))

                if attempt == 2 or delay > 60:
                    raise RuntimeError(
                        f"Telegram unavailable ({code}); retry next run."
                    )

            time.sleep(delay)

    def close(self) -> None:
        self.session.close()


def format_job(job: dict) -> str:
    score = float(job["match_score"])
    indicator = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
    title = escape(str(job["title"])[:200])
    company = escape(str(job["company_name"])[:120])
    location = escape(str(job.get("location") or "Not specified")[:150])
    category = escape(
        str(job.get("category") or "Other").replace("_", " ").title()
    )
    reason = escape(str(job.get("match_reason") or "")[:500])

    lines = [
        f"{indicator} <b>{title}</b>",
        f"{company} · {location}",
        f"<b>Match: {score:.0f}/100</b> · {category}",
    ]

    if reason:
        lines.extend(["", reason])

    url = str(job.get("job_url") or "")
    parsed = urlsplit(url)
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        lines.extend(["", f'<a href="{escape(url, quote=True)}">Apply</a>'])

    return "\n".join(lines)


def notify_pending_jobs(
    database: JobDatabase,
    notifier: TelegramNotifier,
) -> NotificationResult:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE is_baseline = 0
              AND gemini_status IN ('qualified', 'rejected')
              AND match_score IS NOT NULL
              AND notified_at IS NULL
            ORDER BY first_seen_at ASC, fingerprint ASC
            """
        ).fetchall()

    result = NotificationResult(queued=len(rows))

    for row in rows:
        job = dict(row)

        try:
            notifier.send(format_job(job))
        except RuntimeError as error:
            print(f"[TELEGRAM ERROR] {error}")
            result.failed = result.queued - result.sent
            break

        database.mark_notified(job["fingerprint"])
        result.sent += 1
        time.sleep(1.1)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--database", default="data/job_radar.db")
    args = parser.parse_args()

    notifier = TelegramNotifier()
    try:
        if args.test:
            notifier.send("<b>Job Radar</b>\nTelegram connection works.")
            print("Telegram test sent.")
        else:
            database = JobDatabase(args.database)
            database.initialize()
            result = notify_pending_jobs(database, notifier)
            print(
                f"Queued: {result.queued} | "
                f"Sent: {result.sent} | Failed: {result.failed}"
            )
            if result.failed:
                raise SystemExit(1)
    finally:
        notifier.close()


if __name__ == "__main__":
    main()