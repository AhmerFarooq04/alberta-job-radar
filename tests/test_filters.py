from job_radar.filters import (
    has_relevant_title_signal,
    is_clearly_unrelated_role,
    is_entry_level_title,
    is_internship,
    is_senior_role,
    is_target_location,
    is_target_role,
    normalize_text,
    passes_prefilter,
    passes_prefilter_values,
)
from job_radar.models import Job


def make_job(
    *,
    title: str = "Business Systems Analyst",
    location: str = "Edmonton, Alberta",
    employment_type: str | None = "Full-time",
) -> Job:
    """
    Create a reusable Job object for prefilter tests.

    Fields unrelated to filtering receive harmless test values.
    """
    return Job(
        external_id="test-job-001",
        company_id="test-company",
        company_name="Test Company",
        title=title,
        location=location,
        description="Test job description",
        job_url="https://example.com/jobs/test-job-001",
        source="test",
        employment_type=employment_type,
    )


def test_normalize_text() -> None:
    assert normalize_text("Power-BI Developer") == (
        "power bi developer"
    )
    assert normalize_text("Cloud Identity & Access") == (
        "cloud identity and access"
    )
    assert normalize_text(None) == ""


def test_accepts_alberta_locations() -> None:
    assert is_target_location("Edmonton, Alberta")
    assert is_target_location("Calgary, AB, CAN")
    assert is_target_location(
        "Fort McMurray (Base Plant), AB, CAN"
    )
    assert is_target_location("Remote - Alberta")


def test_accepts_ontario_locations() -> None:
    assert is_target_location("Toronto, Ontario")
    assert is_target_location("Ottawa, ON, Canada")
    assert is_target_location("Waterloo")
    assert is_target_location("Mississauga, Ontario")


def test_accepts_canada_remote_locations() -> None:
    assert is_target_location("Remote, Canada")
    assert is_target_location("Canada")
    assert is_target_location("Anywhere in Canada")
    assert is_target_location("Remote")


def test_accepts_missing_location_liberally() -> None:
    assert is_target_location("")
    assert is_target_location(None)


def test_rejects_us_only_locations() -> None:
    assert not is_target_location("Cheyenne, WY, USA")
    assert not is_target_location(
        "New York, United States"
    )
    assert not is_target_location("Remote - US only")


def test_accepts_location_that_includes_canada_and_us() -> None:
    assert is_target_location(
        "Remote - Canada or United States"
    )


def test_rejects_non_target_in_person_canadian_locations() -> None:
    assert not is_target_location(
        "Vancouver, British Columbia"
    )
    assert not is_target_location(
        "Winnipeg, Manitoba"
    )
    assert not is_target_location(
        "Halifax, Nova Scotia"
    )


def test_detects_internships_from_title() -> None:
    assert is_internship("Software Developer Intern")
    assert is_internship("Data Analyst Co-op")
    assert is_internship(
        "Summer Student - Information Technology"
    )


def test_detects_internships_from_employment_type() -> None:
    assert is_internship(
        "Associate Software Developer",
        employment_type="Intern",
    )


def test_detects_entry_level_titles() -> None:
    assert is_entry_level_title("Junior Data Analyst")
    assert is_entry_level_title(
        "Associate Software Developer"
    )
    assert is_entry_level_title(
        "New Graduate Mining Engineer"
    )
    assert is_entry_level_title(
        "Engineer in Training (EIT)"
    )


def test_rejects_clearly_senior_roles() -> None:
    assert is_senior_role("Senior Software Engineer")
    assert is_senior_role("Staff Software Engineer")
    assert is_senior_role("Principal Data Scientist")
    assert is_senior_role("Lead AI Engineer")
    assert is_senior_role(
        "Director of Information Technology"
    )
    assert is_senior_role("Chief Technology Officer")


def test_entry_level_wording_can_override_manager_word() -> None:
    assert not is_senior_role(
        "Associate Product Manager"
    )


def test_keeps_every_kind_of_analyst_role() -> None:
    assert is_target_role("Business Analyst")
    assert is_target_role("Recovery Analyst")
    assert is_target_role("Financial Analyst")
    assert is_target_role("Operations Analyst")
    assert is_target_role("Clinical Data Analyst")
    assert is_target_role("Sales Operations Analyst")
    assert is_target_role(
        "Central Business Systems Applications Analyst"
    )


def test_keeps_technology_and_data_roles() -> None:
    assert is_target_role("Software Developer")
    assert is_target_role(
        "Embedded Software Designer"
    )
    assert is_target_role("Data Engineer")
    assert is_target_role("Power BI Developer")
    assert is_target_role(
        "Cloud Identity & Access Management Engineer"
    )
    assert is_target_role(
        "Forward Deployed Engineer"
    )
    assert is_target_role(
        "Advanced Process Control Engineer"
    )
    assert is_target_role(
        "Go to Market Automation Specialist I"
    )
    assert is_target_role("Hardware Test Engineer")


def test_relevant_signals_are_detected() -> None:
    assert has_relevant_title_signal(
        "Recovery Analyst"
    )
    assert has_relevant_title_signal(
        "Power BI Specialist"
    )
    assert has_relevant_title_signal(
        "Software Designer"
    )
    assert has_relevant_title_signal(
        "Cloud Identity & Access Management Engineer"
    )


def test_rejects_obviously_unrelated_roles() -> None:
    assert is_clearly_unrelated_role(
        "Registered Nurse"
    )
    assert is_clearly_unrelated_role(
        "Account Executive"
    )
    assert is_clearly_unrelated_role(
        "Delivery Driver"
    )
    assert is_clearly_unrelated_role(
        "Warehouse Associate"
    )
    assert is_clearly_unrelated_role(
        "Journeyman Electrician"
    )

    assert not is_target_role("Registered Nurse")
    assert not is_target_role("Account Executive")
    assert not is_target_role("Delivery Driver")
    assert not is_target_role("Warehouse Associate")
    assert not is_target_role(
        "Journeyman Electrician"
    )


def test_relevant_signal_overrides_unrelated_industry_words() -> None:
    assert not is_clearly_unrelated_role(
        "Clinical Data Analyst"
    )
    assert not is_clearly_unrelated_role(
        "Sales Operations Analyst"
    )

    assert is_target_role("Clinical Data Analyst")
    assert is_target_role("Sales Operations Analyst")


def test_keeps_ambiguous_roles_for_gemini() -> None:
    """
    Local filtering must not reject a job merely because its title is not
    present in our preferred-role list.
    """
    assert is_target_role(
        "Process Improvement Coordinator"
    )
    assert is_target_role(
        "Digital Transformation Specialist"
    )
    assert is_target_role("Research Coordinator")
    assert is_target_role(
        "Technical Documentation Specialist"
    )


def test_rejects_internships_by_default() -> None:
    job = make_job(
        title="Data Analyst Intern",
        employment_type="Intern",
    )

    assert not passes_prefilter(job)


def test_can_include_internships_when_requested() -> None:
    job = make_job(
        title="Data Analyst Intern",
        employment_type="Intern",
    )

    assert passes_prefilter(
        job,
        include_internships=True,
    )


def test_complete_prefilter_accepts_relevant_job() -> None:
    job = make_job(
        title="Business Intelligence Analyst",
        location="Calgary, Alberta",
    )

    assert passes_prefilter(job)


def test_complete_prefilter_accepts_ambiguous_job() -> None:
    job = make_job(
        title="Research Coordinator",
        location="Edmonton, Alberta",
    )

    assert passes_prefilter(job)


def test_complete_prefilter_rejects_senior_job() -> None:
    job = make_job(
        title="Lead AI Engineer",
        location="Calgary, Alberta",
    )

    assert not passes_prefilter(job)


def test_complete_prefilter_rejects_unrelated_job() -> None:
    job = make_job(
        title="Registered Nurse",
        location="Edmonton, Alberta",
    )

    assert not passes_prefilter(job)


def test_complete_prefilter_rejects_wrong_location() -> None:
    job = make_job(
        title="Data Analyst",
        location="Cheyenne, WY, USA",
    )

    assert not passes_prefilter(job)


def test_raw_value_prefilter_accepts_relevant_job() -> None:
    assert passes_prefilter_values(
        title="Business Systems Analyst",
        location="Calgary, AB, CAN",
        employment_type="Full time",
    )


def test_raw_value_prefilter_rejects_senior_job() -> None:
    assert not passes_prefilter_values(
        title="Lead AI Engineer",
        location="Edmonton, Alberta",
        employment_type="Full time",
    )


def test_raw_value_prefilter_rejects_us_only_job() -> None:
    assert not passes_prefilter_values(
        title="Data Analyst",
        location="Cheyenne, WY, USA",
        employment_type="Full time",
    )


def test_raw_value_prefilter_respects_internship_setting() -> None:
    assert not passes_prefilter_values(
        title="Data Analyst Intern",
        location="Calgary, Alberta",
        employment_type="Intern",
    )

    assert passes_prefilter_values(
        title="Data Analyst Intern",
        location="Calgary, Alberta",
        employment_type="Intern",
        include_internships=True,
    )