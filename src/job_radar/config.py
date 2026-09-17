from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPANIES_FILE = PROJECT_ROOT / "config" / "companies.yaml"

ATS_REQUIRED_FIELDS = {
    "adp": ("cid", "cc_id"),
    "ashby": ("board",),
    "bamboohr": ("subdomain",),
    "collage": ("site",),
    "dayforce": ("namespace", "board"),
    "deel": ("slug",),
    "greenhouse": ("board",),
    "html_board": (
        "listing_url",
        "link_pattern",
        "title_selector",
        "description_selector",
    ),
    "jsonld": (
        "listing_url",
        "link_pattern",
    ),
    "lever": ("site",),
    "workable": ("account",),
    "workday": (
        "host",
        "tenant",
        "site",
    ),
}


def load_companies() -> list[dict[str, Any]]:
    with COMPANIES_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(
            "companies.yaml must contain a YAML object"
        )

    defaults = config.get("defaults", {})
    companies = config.get("companies", [])

    if not isinstance(defaults, dict):
        raise ValueError(
            "'defaults' must be a YAML object"
        )

    if not isinstance(companies, list):
        raise ValueError(
            "'companies' must be a YAML list"
        )

    validated_companies = []
    seen_ids = set()

    for position, company in enumerate(
        companies,
        start=1,
    ):
        if not isinstance(company, dict):
            raise ValueError(
                f"Company #{position} must be a YAML object"
            )

        merged_company = {
            **defaults,
            **company,
        }

        for field in (
            "id",
            "name",
            "careers_url",
            "ats",
        ):
            if not merged_company.get(field):
                raise ValueError(
                    f"Company #{position} is missing "
                    f"required field: {field}"
                )

        company_id = merged_company["id"]

        if company_id in seen_ids:
            raise ValueError(
                f"Duplicate company ID: {company_id}"
            )

        seen_ids.add(company_id)

        careers_url = merged_company["careers_url"]

        if not careers_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                f"{company_id} has an invalid "
                f"careers URL: {careers_url}"
            )

        ats = merged_company["ats"]

        if not isinstance(ats, dict):
            raise ValueError(
                f"{company_id} must have an ATS object"
            )

        ats_type = ats.get("type")

        if not ats_type:
            raise ValueError(
                f"{company_id} must have an ATS type"
            )

        if ats_type not in ATS_REQUIRED_FIELDS:
            raise ValueError(
                f"{company_id} has unsupported "
                f"ATS type: {ats_type}"
            )

        for ats_field in ATS_REQUIRED_FIELDS[
            ats_type
        ]:
            if not ats.get(ats_field):
                raise ValueError(
                    f"{company_id} uses {ats_type} "
                    f"but is missing ATS field: "
                    f"{ats_field}"
                )

        if merged_company.get("enabled", True):
            validated_companies.append(
                merged_company
            )

    return validated_companies