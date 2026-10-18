import scrapy
from datetime import datetime, timezone
from leadhound.items import RealEstateAgentItem
from leadhound.playwright_utils import playwright_meta


class RealEstateAgentsSpider(scrapy.Spider):
    name = "real_estate_agents"
    allowed_domains = ["nepalyp.com"]
    start_urls = ["https://www.nepalyp.com/category/Estate_agents/city:Kathmandu"]

    def __init__(self, use_playwright="false", *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Spider arguments from -a always arrive as strings, so "false"
        # has to be turned into a real boolean by hand.
        self.use_playwright = str(use_playwright).strip().lower() in ("1", "true", "yes")

    def request_meta(self):
        """Meta for every request: render with Playwright only if asked to."""
        if self.use_playwright:
            return playwright_meta(wait_for_selector="div.company")
        return {}

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, meta=self.request_meta())

    def parse(self, response):
        for company in response.css("div.company"):
            name = company.css(".company_header h3 a::text").get()
            if not name:
                continue

            item = RealEstateAgentItem()
            item["company_id"] = company.attrib.get("data-cmpid")
            item["name"] = name.strip()
            item["profile_url"] = response.urljoin(
                company.css(".company_header h3 a::attr(href)").get()
            )

            address_parts = company.css(".address ::text").getall()
            item["address"] = " ".join(" ".join(address_parts).split())

            item["tagline"] = (company.css(".tagline::text").get() or "").strip() or None

            item["phone"] = company.xpath(
                './/div[@class="s"][.//i[@aria-label="Phone number"]]/span/b/text()'
            ).get()

            established = company.xpath(
                './/div[@class="s"][.//i[@aria-label="Calendar"]]/span/text()'
            ).get()
            item["established_year"] = established.replace("Established", "").strip() if established else None

            years = company.css(".v_years b::text").get()
            item["years_with_us"] = years.strip() if years else None

            item["verified"] = bool(company.css(".v i.fa-check-circle"))

            item["rating"] = company.css(".company_reviews .rate::text").get()
            review_texts = company.css(".company_reviews::text").getall()
            item["review_count"] = next((t.strip() for t in review_texts if "Review" in t), None)

            item["source_url"] = response.url
            item["scraped_at"] = datetime.now(timezone.utc).isoformat()

            yield item

        next_page = response.css('a.pages_arrow[rel="next"]::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse, meta=self.request_meta())