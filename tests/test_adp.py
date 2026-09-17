from job_radar.scrapers.adp import ADPScraper


def make_company():
    return {
        "id": "olympia-trust",
        "name": "Olympia Trust",
        "careers_url": (
            "https://example.com/jobs"
        ),
        "ats": {
            "type": "adp",
            "cid": "company-id",
            "cc_id": "board-id",
            "locale": "en_CA",
        },
        "prefilter_enabled": False,
    }


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "jobRequisitions": [{
                "itemID": "500",
                "requisitionTitle": (
                    "Business Analyst"
                ),
                "jobDescription": (
                    "<p>Analyze operations.</p>"
                ),
                "postDate": (
                    "2026-09-15T00:00:00Z"
                ),
                "workerTypeCode": {
                    "shortName": "Full Time",
                },
                "requisitionLocations": [{
                    "nameCode": {
                        "shortName": (
                            "Calgary, AB"
                        ),
                    },
                }],
            }],
        }


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def get(
        self,
        url,
        params,
        timeout,
    ):
        self.calls += 1

        if self.calls == 1:
            return FakeResponse()

        class EmptyResponse(FakeResponse):
            def json(self):
                return {
                    "jobRequisitions": [],
                }

        return EmptyResponse()


def test_adp_job(
    monkeypatch,
):
    monkeypatch.setattr(
        (
            "job_radar.scrapers.adp"
            ".requests.Session"
        ),
        FakeSession,
    )

    job = ADPScraper(
        make_company()
    ).fetch_jobs()[0]

    assert job.external_id == "500"
    assert (
        job.title
        == "Business Analyst"
    )
    assert job.location == "Calgary, AB"
    assert (
        job.description
        == "Analyze operations."
    )
    assert (
        job.employment_type
        == "Full Time"
    )
    assert job.source == "adp"