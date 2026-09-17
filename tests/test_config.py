import pytest

from job_radar.config import (
    ATS_REQUIRED_FIELDS,
    load_companies,
)
from job_radar.scrapers import (
    SUPPORTED_ATS_TYPES,
)


def test_companies_file_loads():
    companies = load_companies()

    assert companies


def test_at_least_30_companies_exist():
    companies = load_companies()

    assert len(companies) >= 30


def test_company_ids_are_unique():
    companies = load_companies()

    ids = [
        company["id"]
        for company in companies
    ]

    assert len(ids) == len(set(ids))


def test_all_companies_have_locations():
    companies = load_companies()

    for company in companies:
        has_alberta = bool(
            company.get(
                "alberta_locations"
            )
        )

        has_ontario = bool(
            company.get(
                "ontario_locations"
            )
        )

        assert has_alberta or has_ontario, (
            f"{company['name']} has "
            "no target locations"
        )


def test_all_ats_types_are_supported():
    companies = load_companies()

    for company in companies:
        ats_type = company[
            "ats"
        ]["type"]

        assert (
            ats_type
            in SUPPORTED_ATS_TYPES
        ), (
            f"{company['name']} has "
            f"unsupported ATS: {ats_type}"
        )


def test_no_generic_sources_remain():
    companies = load_companies()

    generic_companies = [
        company["name"]
        for company in companies
        if company["ats"]["type"]
        == "generic"
    ]

    assert generic_companies == []


def test_no_google_sheet_sources():
    companies = load_companies()

    google_sheet_companies = [
        company["name"]
        for company in companies
        if company["ats"]["type"]
        == "google_sheet"
    ]

    assert google_sheet_companies == []


def test_required_ats_fields_exist():
    companies = load_companies()

    for company in companies:
        ats = company["ats"]
        ats_type = ats["type"]

        for field in (
            ATS_REQUIRED_FIELDS[
                ats_type
            ]
        ):
            assert ats.get(field), (
                f"{company['name']} "
                f"is missing {field}"
            )


def test_circle_cvi_is_removed():
    companies = load_companies()

    ids = {
        company["id"]
        for company in companies
    }

    assert (
        "circle-cardiovascular-imaging"
        not in ids
    )


def test_loader_rejects_duplicate_ids(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "companies.yaml"

    path.write_text(
        """
companies:
  - id: duplicate
    name: First
    careers_url: https://example.com
    alberta_locations: [Edmonton]
    ats:
      type: lever
      site: first
  - id: duplicate
    name: Second
    careers_url: https://example.com
    alberta_locations: [Calgary]
    ats:
      type: lever
      site: second
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "job_radar.config.COMPANIES_FILE",
        path,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate company ID",
    ):
        load_companies()