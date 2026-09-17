from __future__ import annotations

import re
import unicodedata

from job_radar.models import Job


# ---------------------------------------------------------------------------
# Geographic filtering
# ---------------------------------------------------------------------------

ALBERTA_LOCATION_TERMS = (
    "alberta",
    "ab",
    "edmonton",
    "calgary",
    "fort mcmurray",
    "red deer",
    "lethbridge",
    "medicine hat",
    "grande prairie",
    "st albert",
    "sherwood park",
    "spruce grove",
    "airdrie",
    "cochrane",
    "lloydminster",
    "okotoks",
    "rocky view",
)

ONTARIO_LOCATION_TERMS = (
    "ontario",
    "on",
    "toronto",
    "ottawa",
    "mississauga",
    "brampton",
    "hamilton",
    "waterloo",
    "kitchener",
    "cambridge",
    "guelph",
    "london",
    "markham",
    "vaughan",
    "oakville",
    "burlington",
    "richmond hill",
    "scarborough",
    "north york",
)

REMOTE_TERMS = (
    "remote",
    "work from home",
    "work-from-home",
    "virtual",
    "anywhere in canada",
    "canada remote",
    "remote canada",
)

CANADA_TERMS = (
    "canada",
    "can",
    "canadian",
)

US_ONLY_TERMS = (
    "united states",
    "usa",
    "u.s.",
    "u.s.a.",
    "us only",
)

FOREIGN_LOCATION_TERMS = (
    "united kingdom",
    "uk",
    "england",
    "india",
    "united arab emirates",
    "uae",
    "australia",
    "germany",
    "france",
    "singapore",
    "philippines",
)

UNKNOWN_LOCATION_TERMS = (
    "not specified",
    "location not specified",
    "multiple locations",
    "various locations",
)

NON_TARGET_CANADIAN_PROVINCES = (
    "british columbia",
    "bc",
    "saskatchewan",
    "sk",
    "manitoba",
    "mb",
    "quebec",
    "qc",
    "nova scotia",
    "ns",
    "new brunswick",
    "nb",
    "newfoundland",
    "nl",
    "prince edward island",
    "pei",
    "northwest territories",
    "nwt",
    "nunavut",
    "yukon",
)


# ---------------------------------------------------------------------------
# Career-level filtering
# ---------------------------------------------------------------------------

INTERNSHIP_TERMS = (
    "intern",
    "internship",
    "co-op",
    "coop",
    "co op",
    "student",
    "summer student",
    "placement student",
)

SENIOR_LEVEL_TERMS = (
    "senior",
    "sr",
    "principal",
    "staff",
    "director",
    "head of",
    "vice president",
    "vp",
    "lead",
    "manager",
    "architect",
    "chief",
)

ENTRY_LEVEL_TERMS = (
    "junior",
    "jr",
    "associate",
    "entry level",
    "entry-level",
    "new graduate",
    "new grad",
    "graduate",
    "engineer in training",
    "eit",
    "specialist i",
    "analyst i",
    "developer i",
    "engineer i",
)


# ---------------------------------------------------------------------------
# Titles we definitely want Gemini to inspect
# ---------------------------------------------------------------------------

RELEVANT_TITLE_TERMS = (
    # Keep every kind of analyst role.
    "analyst",
    "analysis",
    "analytics",

    # Data and business intelligence.
    "data",
    "business intelligence",
    "bi developer",
    "bi specialist",
    "power bi",
    "reporting",
    "insights",
    "visualization",
    "database",

    # Software and application development.
    "software",
    "developer",
    "programmer",
    "application",
    "web",
    "full stack",
    "full-stack",
    "frontend",
    "front-end",
    "backend",
    "back-end",
    "mobile developer",
    "software designer",
    "embedded",

    # IT, infrastructure, cloud, and security.
    "information technology",
    "it support",
    "technical support",
    "service desk",
    "help desk",
    "systems",
    "system administrator",
    "network",
    "cloud",
    "devops",
    "platform",
    "infrastructure",
    "cybersecurity",
    "cyber security",
    "information security",
    "identity access management",
    "identity and access management",
    "iam",

    # Testing and quality.
    "quality assurance",
    "qa",
    "test engineer",
    "test developer",
    "software tester",
    "automation",
    "automated testing",

    # AI and machine learning.
    "artificial intelligence",
    "machine learning",
    "ai engineer",
    "ml engineer",

    # Product, projects, operations, and implementation.
    "product",
    "project coordinator",
    "project analyst",
    "business systems",
    "business operations",
    "operations analyst",
    "implementation",
    "technical consultant",
    "technology consultant",
    "solutions consultant",
    "forward deployed engineer",
    "process control",
    "digital transformation",
    "process improvement",
)


# ---------------------------------------------------------------------------
# Obviously unrelated jobs
#
# Relevant terms take priority over these exclusions. For example:
#
#   Clinical Data Analyst -> kept because it contains data and analyst.
#   Sales Operations Analyst -> kept because it contains analyst.
#   Registered Nurse -> rejected.
# ---------------------------------------------------------------------------

CLEARLY_UNRELATED_TITLE_TERMS = (
    # Medicine and direct patient care.
    "registered nurse",
    "licensed practical nurse",
    "nurse practitioner",
    "physician",
    "surgeon",
    "dentist",
    "dental hygienist",
    "pharmacist",
    "pharmacy assistant",
    "paramedic",
    "medical doctor",
    "clinical therapist",
    "physiotherapist",
    "occupational therapist",
    "veterinarian",
    "veterinary technician",

    # Pure sales and retail.
    "account executive",
    "sales representative",
    "sales associate",
    "sales development representative",
    "business development representative",
    "territory sales",
    "retail associate",
    "cashier",
    "store associate",
    "store clerk",

    # Food and hospitality.
    "cook",
    "chef",
    "server",
    "bartender",
    "dishwasher",
    "housekeeper",
    "room attendant",
    "food service",
    "restaurant supervisor",

    # Driving, warehouse, and physical operations.
    "truck driver",
    "delivery driver",
    "bus driver",
    "warehouse worker",
    "warehouse associate",
    "material handler",
    "forklift operator",
    "general labourer",
    "general laborer",
    "construction labourer",
    "construction laborer",
    "equipment operator",

    # Skilled trades.
    "electrician",
    "plumber",
    "welder",
    "pipefitter",
    "millwright",
    "carpenter",
    "heavy duty mechanic",
    "automotive mechanic",
    "hvac technician",

    # Other clearly unrelated work.
    "security guard",
    "custodian",
    "janitor",
    "groundskeeper",

        # Recruiting and human resources.
    "talent acquisition",
    "recruiter",
    "human resources",
    "people business partner",

    # Accounting roles without an analyst or data signal.
    "accountant",
    "bookkeeper",

    # Physical production roles.
    "terminal operator",
    "plant operator",
    "production technician",
    "production framer",
    "site framer",

    # Generic evergreen postings that are not real vacancies.
    "general application",
    "general applications",
    "talent network",
    "join our network",
    "want to work with us",
)


def normalize_text(value: str | None) -> str:
    """
    Normalize text so matching is predictable.

    Examples:
        "Power-BI Developer" -> "power bi developer"
        "Cloud Identity & Access" -> "cloud identity and access"
        "Sr. Analyst" -> "sr analyst"
    """
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9+#]+", " ", normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def contains_term(
    text: str | None,
    terms: tuple[str, ...],
) -> bool:
    """
    Check for whole words or whole phrases.

    Padding both values with spaces prevents terms such as "sales" from
    accidentally matching a word such as "Salesforce".
    """
    normalized_text = f" {normalize_text(text)} "

    return any(
        f" {normalize_text(term)} " in normalized_text
        for term in terms
    )


def is_target_location(location: str | None) -> bool:
    """
    Determine whether a job location is acceptable.

    Accepted:
    - Alberta
    - Ontario
    - Remote roles without an explicit foreign restriction
    - Canada-wide roles
    - Missing or explicitly unspecified locations

    Rejected:
    - US-only roles, even when they say "remote"
    - Clearly foreign roles
    - Roles in non-target Canadian provinces
    - Unknown named locations such as Vancouver, Noida, or Coimbatore
    """
    normalized_location = normalize_text(location)

    # A genuinely missing location is worth keeping for later inspection.
    if not normalized_location:
        return True

    if contains_term(
        normalized_location,
        UNKNOWN_LOCATION_TERMS,
    ):
        return True

    mentions_canada = contains_term(
        normalized_location,
        CANADA_TERMS,
    )
    mentions_us = contains_term(
        normalized_location,
        US_ONLY_TERMS,
    )

    # This check must happen before checking for "remote".
    if mentions_us and not mentions_canada:
        return False

    # Prevent "London, UK" from matching the Ontario city of London.
    if contains_term(
        normalized_location,
        FOREIGN_LOCATION_TERMS,
    ):
        return False

    # Alberta or Ontario wins when a posting lists several locations.
    if contains_term(
        normalized_location,
        ALBERTA_LOCATION_TERMS,
    ):
        return True

    if contains_term(
        normalized_location,
        ONTARIO_LOCATION_TERMS,
    ):
        return True

    # "Remote in Quebec" should not pass merely because it says remote.
    if contains_term(
        normalized_location,
        NON_TARGET_CANADIAN_PROVINCES,
    ):
        return False

    if contains_term(
        normalized_location,
        REMOTE_TERMS,
    ):
        return True

    # "Canada" by itself commonly means Canada-wide.
    if mentions_canada:
        return True

    # A named but unrecognized location is outside our target area.
    return False


def is_internship(
    title: str | None,
    employment_type: str | None = None,
) -> bool:
    """
    Determine whether a job is an internship or student position.
    """
    combined = " ".join(
        value
        for value in (title, employment_type)
        if value
    )

    return contains_term(combined, INTERNSHIP_TERMS)


def is_entry_level_title(title: str | None) -> bool:
    """
    Determine whether a title explicitly describes an early-career role.
    """
    return contains_term(title, ENTRY_LEVEL_TERMS)


def is_senior_role(title: str | None) -> bool:
    """
    Determine whether a title is clearly senior or managerial.

    Explicit early-career wording wins. This prevents a title such as
    "Associate Product Manager" from being rejected merely because it
    includes the word "manager".
    """
    if is_entry_level_title(title):
        return False

    return contains_term(title, SENIOR_LEVEL_TERMS)


def has_relevant_title_signal(title: str | None) -> bool:
    """
    Determine whether a title contains a role category we definitely want
    Gemini to inspect.
    """
    return contains_term(title, RELEVANT_TITLE_TERMS)


def is_clearly_unrelated_role(title: str | None) -> bool:
    """
    Determine whether a job is unmistakably outside the intended search.

    Relevant signals take priority. Therefore, "Clinical Data Analyst"
    remains eligible even though the job is related to medicine.
    """
    if has_relevant_title_signal(title):
        return False

    return contains_term(
        title,
        CLEARLY_UNRELATED_TITLE_TERMS,
    )


def is_target_role(title: str | None) -> bool:
    """
    Determine whether a title is plausible enough for Gemini.

    This is an exclusion-based filter. Ambiguous jobs are retained.
    """
    if not title or not title.strip():
        return True

    if is_senior_role(title):
        return False

    if is_clearly_unrelated_role(title):
        return False

    return True


def passes_prefilter_values(
    title: str | None,
    location: str | None,
    employment_type: str | None = None,
    include_internships: bool = False,
) -> bool:
    """
    Apply the prefilter directly to raw field values.

    Structured scrapers use this before downloading or constructing a
    complete Job object. Workday uses this function to avoid downloading
    full descriptions for obviously unsuitable jobs.
    """
    if not is_target_location(location):
        return False

    if (
        not include_internships
        and is_internship(title, employment_type)
    ):
        return False

    if not is_target_role(title):
        return False

    return True


def passes_prefilter(
    job: Job,
    include_internships: bool = False,
) -> bool:
    """
    Apply the prefilter to a completed Job object.

    This filter only answers:

        "Is this job plausible enough to send to Gemini?"

    It does not determine whether the candidate is qualified.
    """
    return passes_prefilter_values(
        title=job.title,
        location=job.location,
        employment_type=job.employment_type,
        include_internships=include_internships,
    )