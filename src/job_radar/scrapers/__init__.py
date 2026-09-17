from job_radar.scrapers.adp import ADPScraper
from job_radar.scrapers.ashby import AshbyScraper
from job_radar.scrapers.bamboohr import BambooHRScraper
from job_radar.scrapers.base import BaseScraper
from job_radar.scrapers.collage import CollageScraper
from job_radar.scrapers.dayforce import DayforceScraper
from job_radar.scrapers.deel import DeelScraper
from job_radar.scrapers.greenhouse import GreenhouseScraper
from job_radar.scrapers.html_board import HtmlBoardScraper
from job_radar.scrapers.jsonld import JsonLdScraper
from job_radar.scrapers.lever import LeverScraper
from job_radar.scrapers.workable import WorkableScraper
from job_radar.scrapers.workday import WorkdayScraper


SCRAPER_CLASSES = {
    "adp": ADPScraper,
    "ashby": AshbyScraper,
    "bamboohr": BambooHRScraper,
    "collage": CollageScraper,
    "dayforce": DayforceScraper,
    "deel": DeelScraper,
    "greenhouse": GreenhouseScraper,
    "html_board": HtmlBoardScraper,
    "jsonld": JsonLdScraper,
    "lever": LeverScraper,
    "workable": WorkableScraper,
    "workday": WorkdayScraper,
}

SUPPORTED_ATS_TYPES = frozenset(SCRAPER_CLASSES)


def create_scraper(company: dict) -> BaseScraper:
    ats_type = company["ats"]["type"]
    scraper_class = SCRAPER_CLASSES.get(ats_type)

    if scraper_class is None:
        raise ValueError(
            f"Unsupported ATS type: {ats_type}"
        )

    return scraper_class(company)