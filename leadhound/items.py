import scrapy


class RealEstateAgentItem(scrapy.Item):
    company_id = scrapy.Field()
    name = scrapy.Field()
    profile_url = scrapy.Field()
    address = scrapy.Field()
    tagline = scrapy.Field()
    phone = scrapy.Field()
    established_year = scrapy.Field()
    years_with_us = scrapy.Field()
    verified = scrapy.Field()
    rating = scrapy.Field()
    review_count = scrapy.Field()
    source_url = scrapy.Field()
    scraped_at = scrapy.Field()