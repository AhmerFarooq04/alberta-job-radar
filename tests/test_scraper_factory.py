import pytest

from job_radar.scrapers import (
    SCRAPER_CLASSES,
    SUPPORTED_ATS_TYPES,
    create_scraper,
)


COMPANIES = {
    "adp": {
        "cid": "test-cid",
        "cc_id": "test-board",
    },
    "ashby": {
        "board": "test",
    },
    "bamboohr": {
        "subdomain": "test",
    },
    "collage": {
        "site": "test",
    },
    "dayforce": {
        "namespace": "test",
        "board": "test",
    },
    "deel": {
        "slug": "test",
    },
    "greenhouse": {
        "board": "test",
    },
    "html_board": {
        "listing_url": (
            "https://example.com/jobs"
        ),
        "link_pattern": (
            "example[.]com/jobs/.+"
        ),
        "title_selector": "h1",
        "description_selector": "main",
    },
    "jsonld": {
        "listing_url": (
            "https://example.com/jobs"
        ),
        "link_pattern": (
            "example[.]com/jobs/.+"
        ),
    },
    "lever": {
        "site": "test",
    },
    "workable": {
        "account": "test",
    },
    "workday": {
        "host": (
            "test.wd1.myworkdayjobs.com"
        ),
        "tenant": "test",
        "site": "External",
    },
}


def make_company(
    ats_type,
):
    return {
        "id": f"test-{ats_type}",
        "name": f"Test {ats_type}",
        "careers_url": (
            "https://example.com/jobs"
        ),
        "ats": {
            "type": ats_type,
            **COMPANIES[ats_type],
        },
    }


@pytest.mark.parametrize(
    "ats_type",
    sorted(COMPANIES),
)
def test_factory_creates_scraper(
    ats_type,
):
    company = make_company(ats_type)

    scraper = create_scraper(company)

    assert isinstance(
        scraper,
        SCRAPER_CLASSES[ats_type],
    )


def test_supported_types_match_factory():
    assert SUPPORTED_ATS_TYPES == frozenset(
        SCRAPER_CLASSES
    )


def test_factory_rejects_unknown_type():
    company = {
        "id": "unknown",
        "name": "Unknown",
        "careers_url": (
            "https://example.com"
        ),
        "ats": {
            "type": "unknown",
        },
    }

    with pytest.raises(
        ValueError,
        match="Unsupported ATS type",
    ):
        create_scraper(company)