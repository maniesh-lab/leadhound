import scrapy
from datetime import datetime, timezone
from leadhound.items import RealEstateAgentItem


class RealEstateAgentsSpider(scrapy.Spider):
    name = "real_estate_agents"
    allowed_domains = ["nepalyp.com"]
    start_urls = ["https://www.nepalyp.com/category/Estate_agents/city:Kathmandu"]

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
            yield response.follow(next_page, callback=self.parse)