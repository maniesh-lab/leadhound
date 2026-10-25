"""
Spider tests against REAL saved nepalyp.com pages (tests/fixtures/), saved in
Oct 2026: the first results page and the last one (page 8).

Why: test_spider.py uses a small hand-written page, which proves the logic
but can't notice when the real site's HTML is different. These pages are
copies of the real thing (only the site's map API key was swapped for
"REDACTED"), so if the selectors stop matching real markup, these fail.

No network: the saved HTML is fed straight into the spider.
To refresh a fixture, save the page again with curl (see README, "How CI Works").
"""

from pathlib import Path

from scrapy.exporters import CsvItemExporter
from scrapy.http import HtmlResponse, Request

from leadhound import quality
from leadhound.items import RealEstateAgentItem
from leadhound.pipelines import CleaningPipeline, DedupPipeline, ValidationPipeline
from leadhound.spiders.real_estate_agents import RealEstateAgentsSpider

FIXTURES = Path(__file__).parent / "fixtures"
FIRST_URL = "https://www.nepalyp.com/category/Estate_agents/city:Kathmandu"
LAST_URL = "https://www.nepalyp.com/category/Estate_agents/8/city:Kathmandu"


def parse_fixture(filename, url):
    """Run the spider's parse() on a saved page. Returns (items, follow-up requests)."""
    body = (FIXTURES / filename).read_bytes()
    response = HtmlResponse(url=url, body=body, encoding="utf-8", request=Request(url))
    results = list(RealEstateAgentsSpider().parse(response))
    items = [r for r in results if isinstance(r, RealEstateAgentItem)]
    requests = [r for r in results if isinstance(r, Request)]
    return items, requests


def run_pipelines(items):
    """Push items through the same three pipelines settings.py uses, in order."""
    pipelines = [ValidationPipeline(), CleaningPipeline(), DedupPipeline()]
    for item in items:
        for pipeline in pipelines:
            item = pipeline.process_item(item, spider=None)
    return items


# --- first page ---

def test_first_page_has_twenty_listings():
    # The page also has an ad block with class="company" but no name; it must be skipped.
    items, _ = parse_fixture("listing_page_first.html", FIRST_URL)
    assert len(items) == 20


def test_first_page_full_listing():
    items, _ = parse_fixture("listing_page_first.html", FIRST_URL)
    excom = items[0]
    assert excom["company_id"] == "65740"
    assert excom["name"] == "EXCOM GROUP (P) Ltd"
    assert excom["profile_url"] == "https://www.nepalyp.com/company/65740/EXCOM_GROUP_P_Ltd"
    assert excom["tagline"] == "Connecting buyers and sellers for real estate success."
    assert excom["phone"] == "977-1-4416941/43"
    assert excom["established_year"] == "2017"  # real page says "2017 Established"
    assert excom["years_with_us"] == "+9"
    assert excom["verified"] is True
    assert excom["rating"] == "5.0"
    assert excom["review_count"] == "3 Reviews"


def test_first_page_unverified_listing():
    items, _ = parse_fixture("listing_page_first.html", FIRST_URL)
    so_real_estate = items[2]
    assert so_real_estate["name"] == "S.O. Real Estate"
    assert so_real_estate["verified"] is False
    assert so_real_estate["years_with_us"] is None
    assert so_real_estate["tagline"] is None
    assert so_real_estate["rating"] is None
    assert so_real_estate["phone"] == "+9779745616809"


def test_first_page_follows_next_page():
    _, requests = parse_fixture("listing_page_first.html", FIRST_URL)
    assert [r.url for r in requests] == ["https://www.nepalyp.com/category/Estate_agents/2/city:Kathmandu"]


# --- last page ---

def test_last_page_has_two_listings():
    items, _ = parse_fixture("listing_page_last.html", LAST_URL)
    assert [i["name"] for i in items] == ["Valuable Housing", "Valley Management and Suppliers Service"]


def test_last_page_stops_paginating():
    # The real last page has a "prev" arrow but no "next" one.
    _, requests = parse_fixture("listing_page_last.html", LAST_URL)
    assert requests == []


# --- whole chain: real page -> spider -> pipelines -> CSV -> data-quality check ---

def test_cleaned_values_from_real_page():
    items, _ = parse_fixture("listing_page_first.html", FIRST_URL)
    excom = run_pipelines(items)[0]
    assert excom["address"] == "Sixth Floor, Four Square Complex, Naxal, Kathmandu, Nepal"
    assert excom["rating"] == 5.0
    assert excom["review_count"] == 3


def test_real_pages_produce_a_csv_that_passes_quality_checks(tmp_path):
    first, _ = parse_fixture("listing_page_first.html", FIRST_URL)
    last, _ = parse_fixture("listing_page_last.html", LAST_URL)
    items = run_pipelines(first + last)

    csv_path = tmp_path / "leads.csv"
    with open(csv_path, "wb") as f:
        exporter = CsvItemExporter(f)  # the same exporter `scrapy crawl -O x.csv` uses
        exporter.start_exporting()
        for item in items:
            exporter.export_item(item)
        exporter.finish_exporting()

    report = quality.check_csv(str(csv_path), min_rows=22)
    assert report.problems == []
    assert report.status == "passed"
