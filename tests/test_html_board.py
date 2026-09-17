from job_radar.scrapers.html_board import (
    HtmlBoardScraper,
)


def make_company():
    return {
        "id": "test-company",
        "name": "Test Company",
        "careers_url": (
            "https://example.com/careers"
        ),
        "ats": {
            "type": "html_board",
            "listing_url": (
                "https://example.com/careers"
            ),
            "link_pattern": (
                "example[.]com/careers/"
                "[^/]+/$"
            ),
            "title_selector": "h1",
            "description_selector": "main",
            "location_regex": (
                "(Calgary, AB)"
            ),
            "employment_regex": (
                "(Full Time)"
            ),
        },
        "prefilter_enabled": False,
    }


class FakeResponse:
    def __init__(
        self,
        text,
        url,
    ):
        self.text = text
        self.url = url

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.headers = {}

    def get(
        self,
        url,
        timeout,
    ):
        if url.endswith("/careers"):
            return FakeResponse(
                (
                    '<a href="/careers/'
                    'data-analyst/">'
                    "Data Analyst"
                    "</a>"
                ),
                url,
            )

        return FakeResponse(
            """
<html>
<body>
<h1>Data Analyst</h1>
<div>Calgary, AB</div>
<div>Full Time</div>
<main>
<p>Analyze business data.</p>
</main>
</body>
</html>
""",
            url,
        )


def test_html_board_job(
    monkeypatch,
):
    monkeypatch.setattr(
        (
            "job_radar.scrapers.html_board"
            ".requests.Session"
        ),
        FakeSession,
    )

    job = HtmlBoardScraper(
        make_company()
    ).fetch_jobs()[0]

    assert (
        job.external_id
        == "data-analyst"
    )
    assert job.title == "Data Analyst"
    assert job.location == "Calgary, AB"
    assert (
        job.employment_type
        == "Full Time"
    )
    assert (
        job.description
        == "Analyze business data."
    )
    assert job.source == "html_board"