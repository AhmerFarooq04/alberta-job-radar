import time

import requests

from job_radar.config import load_companies


TIMEOUT_SECONDS = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; AlbertaJobRadar/0.1)"
    )
}


def get_test_url(
    company: dict,
) -> str:
    ats = company["ats"]
    ats_type = ats["type"]

    if ats_type == "lever":
        return (
            "https://api.lever.co/v0/"
            f"postings/{ats['site']}"
            "?mode=json"
        )

    if ats_type == "greenhouse":
        return (
            "https://boards-api.greenhouse.io/"
            "v1/boards/"
            f"{ats['board']}/jobs"
            "?content=true"
        )

    if ats_type == "ashby":
        return (
            "https://api.ashbyhq.com/"
            "posting-api/job-board/"
            f"{ats['board']}"
        )

    if ats_type == "bamboohr":
        return (
            f"https://{ats['subdomain']}"
            ".bamboohr.com/careers/list"
        )

    if ats_type == "dayforce":
        culture = ats.get(
            "culture",
            "en-US",
        )

        return (
            "https://jobs.dayforcehcm.com/"
            f"{culture}/"
            f"{ats['namespace']}/"
            f"{ats['board']}"
        )

    if ats_type == "workable":
        return (
            "https://apply.workable.com/"
            f"{ats['account']}/"
        )

    if ats_type == "adp":
        return (
            "https://workforcenow.adp.com/"
            "mascsr/default/careercenter/"
            "public/events/staffing/v1/"
            "job-requisitions"
            f"?cid={ats['cid']}"
            f"&ccId={ats['cc_id']}"
        )

    if ats_type == "collage":
        return (
            "https://api.collage.co/v1/"
            f"positions/{ats['site']}"
        )

    if ats_type == "deel":
        return (
            "https://jobs.deel.com/"
            f"{ats['slug']}"
        )

    if ats_type in {
        "jsonld",
        "html_board",
    }:
        return ats["listing_url"]

    return company.get(
        "jobs_url",
        company["careers_url"],
    )


def check_company(
    company: dict,
) -> dict:
    test_url = get_test_url(company)

    try:
        response = requests.get(
            test_url,
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=True,
        )

        return {
            "company": company["name"],
            "ats": company["ats"]["type"],
            "status": response.status_code,
            "working": response.ok,
            "content_type": (
                response.headers.get(
                    "content-type",
                    "unknown",
                )
            ),
            "final_url": response.url,
            "error": None,
        }

    except requests.RequestException as error:
        return {
            "company": company["name"],
            "ats": company["ats"]["type"],
            "status": None,
            "working": False,
            "content_type": None,
            "final_url": test_url,
            "error": str(error),
        }


def main() -> None:
    companies = load_companies()

    working_count = 0
    failed_count = 0

    print(
        f"Checking {len(companies)} "
        "configured companies...\n"
    )

    for company in companies:
        result = check_company(company)

        if result["working"]:
            working_count += 1
            status = "PASS"
        else:
            failed_count += 1
            status = "FAIL"

        print(
            f"[{status}] "
            f"{result['company']} | "
            f"ATS={result['ats']} | "
            f"HTTP={result['status']}"
        )

        if result["error"]:
            print(
                f"       Error: "
                f"{result['error']}"
            )
        else:
            print(
                f"       URL: "
                f"{result['final_url']}"
            )

        time.sleep(
            company.get(
                "request_delay_seconds",
                2,
            )
        )

    print("\nSource check complete")
    print(f"Working: {working_count}")
    print(f"Failed:  {failed_count}")


if __name__ == "__main__":
    main()