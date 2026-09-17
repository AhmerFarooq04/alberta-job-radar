import html
from abc import ABC, abstractmethod
from html.parser import HTMLParser

from job_radar.models import Job


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned_data = data.strip()

        if cleaned_data:
            self.parts.append(cleaned_data)


def html_to_text(value: str) -> str:
    """Convert an HTML job description into normalized plain text."""

    if not value:
        return ""

    decoded_value = html.unescape(value)

    parser = _HTMLTextExtractor()
    parser.feed(decoded_value)

    plain_text = " ".join(parser.parts)

    return " ".join(plain_text.split())


class BaseScraper(ABC):
    def __init__(self, company: dict):
        self.company = company

    @abstractmethod
    def fetch_jobs(self) -> list[Job]:
        """Download and return all currently published jobs."""
        raise NotImplementedError