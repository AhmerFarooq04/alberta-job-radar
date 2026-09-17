from job_radar.scrapers.collage import (
    CollageScraper,
)


def make_company():
    return {
        "id": "veerum",
        "name": "VEERUM",
        "careers_url": (
            "https://veerum.com/careers"
        ),
        "ats": {
            "type": "collage",
            "site": "veerum",
        },
        "prefilter_enabled": False,
    }


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "positions": [{
                "id": "900",
                "title": "Data Analyst",
                "location": "Calgary, AB",
                "employmentType": (
                    "Full Time"
                ),
                "workplaceType": "Hybrid",
                "description": (
                    "<p>Analyze industrial data.</p>"
                ),
                "hostedUrl": (
                    "https://example.com/jobs/900"
                ),
            }],
        }


def test_collage_job(
    monkeypatch,
):
    monkeypatch.setattr(
        (
            "job_radar.scrapers.collage"
            ".requests.get"
        ),
        lambda *args, **kwargs: (
            FakeResponse()
        ),
    )

    job = CollageScraper(
        make_company()
    ).fetch_jobs()[0]

    assert job.external_id == "900"
    assert job.title == "Data Analyst"
    assert job.location == "Calgary, AB"
    assert job.description == (
        "Analyze industrial data."
    )
    assert job.source == "collage"