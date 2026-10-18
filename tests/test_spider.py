"""
Tests for the spider's parsing logic, run against a small hand-written
HTML page shaped like a nepalyp.com listing page. No network needed.
"""

from scrapy.http import HtmlResponse, Request

from leadhound.items import RealEstateAgentItem
from leadhound.spiders.real_estate_agents import RealEstateAgentsSpider

PAGE_URL = "https://www.nepalyp.com/category/Estate_agents/city:Kathmandu"

LISTING_HTML = """
<html><body>
  <div class="company" data-cmpid="65740">
    <div class="company_header"><h3><a href="/company/65740/EXCOM_GROUP">EXCOM GROUP (P) Ltd</a></h3></div>
    <div class="address">Sixth Floor, <span>Naxal</span> , Kathmandu</div>
    <div class="tagline"> Connecting buyers and sellers. </div>
    <div class="s"><i aria-label="Phone number"></i><span><b>977-1-4416941/43</b></span></div>
    <div class="s"><i aria-label="Calendar"></i><span>Established 2017</span></div>
    <div class="v_years"><b>+9</b></div>
    <div class="v"><i class="fa fa-check-circle"></i></div>
    <div class="company_reviews"><span class="rate">5.0</span> 3 Reviews</div>
  </div>
  <div class="company" data-cmpid="27854">
    <div class="company_header"><h3><a href="/company/27854/Maharjan">Maharjan Builders</a></h3></div>
    <div class="address">Teku, Kathmandu</div>
  </div>
  <div class="company"><div class="company_header"><h3></h3></div></div>
  <a class="pages_arrow" rel="next" href="/category/Estate_agents/2/city:Kathmandu">Next</a>
</body></html>
"""


def fake_response(html=LISTING_HTML):
    return HtmlResponse(url=PAGE_URL, body=html, encoding="utf-8", request=Request(PAGE_URL))


def parse_all(spider, html=LISTING_HTML):
    results = list(spider.parse(fake_response(html)))
    items = [r for r in results if isinstance(r, RealEstateAgentItem)]
    requests = [r for r in results if isinstance(r, Request)]
    return items, requests


def test_parses_full_listing():
    items, _ = parse_all(RealEstateAgentsSpider())
    first = items[0]
    assert first["company_id"] == "65740"
    assert first["name"] == "EXCOM GROUP (P) Ltd"
    assert first["profile_url"] == "https://www.nepalyp.com/company/65740/EXCOM_GROUP"
    assert first["phone"] == "977-1-4416941/43"
    assert first["established_year"] == "2017"
    assert first["years_with_us"] == "+9"
    assert first["verified"] is True
    assert first["rating"] == "5.0"
    assert first["review_count"] == "3 Reviews"
    assert first["tagline"] == "Connecting buyers and sellers."


def test_sparse_listing_gets_empty_optional_fields():
    items, _ = parse_all(RealEstateAgentsSpider())
    sparse = items[1]
    assert sparse["name"] == "Maharjan Builders"
    assert sparse["tagline"] is None
    assert sparse["phone"] is None
    assert sparse["verified"] is False


def test_listing_without_name_is_skipped():
    items, _ = parse_all(RealEstateAgentsSpider())
    assert len(items) == 2


def test_follows_next_page():
    _, requests = parse_all(RealEstateAgentsSpider())
    assert len(requests) == 1
    assert requests[0].url == "https://www.nepalyp.com/category/Estate_agents/2/city:Kathmandu"


def test_stops_on_last_page():
    last_page = LISTING_HTML.replace('rel="next"', 'rel="prev"')
    _, requests = parse_all(RealEstateAgentsSpider(), last_page)
    assert requests == []


def test_playwright_off_by_default():
    spider = RealEstateAgentsSpider()
    assert spider.request_meta() == {}
    _, requests = parse_all(spider)
    assert "playwright" not in requests[0].meta


def test_playwright_flag_turns_it_on_for_every_request():
    spider = RealEstateAgentsSpider(use_playwright="true")
    meta = spider.request_meta()
    assert meta["playwright"] is True
    assert meta["playwright_page_methods"][0].args == ("div.company",)
    _, requests = parse_all(spider)
    assert requests[0].meta["playwright"] is True


def test_playwright_flag_false_string_means_off():
    assert RealEstateAgentsSpider(use_playwright="false").use_playwright is False
