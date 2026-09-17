from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    external_id: str
    company_id: str
    company_name: str
    title: str
    location: str
    description: str
    job_url: str
    source: str
    posted_at: datetime | None = None
    posted_text: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None