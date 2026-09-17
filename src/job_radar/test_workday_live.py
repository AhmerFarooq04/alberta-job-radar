from job_radar.config import load_companies
from job_radar.scrapers.workday import (
    WorkdayScraper,
)


def main() -> None:
    companies = load_companies()

    workday_companies = [
        company
        for company in companies
        if company["ats"]["type"] == "workday"
    ]

    if not workday_companies:
        print("No Workday companies were found.")
        return

    for company in workday_companies:
        # Smoke tests check the raw Workday adapter rather than our
        # relevance filter.
        test_company = {
            **company,
            "max_jobs": 5,
            "prefilter_enabled": False,
        }

        print()
        print("=" * 72)
        print(f"Testing: {test_company['name']}")
        print("=" * 72)
        print(
            "Only the first five raw jobs "
            "will be downloaded.\n"
        )

        try:
            scraper = WorkdayScraper(
                test_company
            )

            jobs = scraper.fetch_jobs()

            print(
                "Jobs downloaded for test: "
                f"{len(jobs)}\n"
            )

            for job in jobs:
                print(f"Title:       {job.title}")
                print(
                    f"Location:    {job.location}"
                )
                print(
                    f"Posted:      "
                    f"{job.posted_text}"
                )
                print(
                    "Employment:  "
                    f"{job.employment_type}"
                )
                print(
                    "Workplace:   "
                    f"{job.workplace_type}"
                )
                print(
                    "Description: "
                    f"{len(job.description)} "
                    "characters"
                )
                print(
                    f"URL:         {job.job_url}"
                )
                print()

        except Exception as error:
            print(
                f"ERROR: {type(error).__name__}: "
                f"{error}"
            )


if __name__ == "__main__":
    main()