import re
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class ValidationPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if not adapter.get("name") or not adapter.get("profile_url"):
            raise DropItem(f"Missing required field(s) in: {dict(adapter)}")
        return item


class CleaningPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)

        address = adapter.get("address")
        if address:
            cleaned = re.sub(r"\s+,", ",", address)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            adapter["address"] = cleaned

        review_count = adapter.get("review_count")
        if review_count:
            match = re.search(r"\d+", review_count)
            adapter["review_count"] = int(match.group()) if match else None

        rating = adapter.get("rating")
        if rating:
            try:
                adapter["rating"] = float(rating)
            except ValueError:
                adapter["rating"] = None

        return item


class DedupPipeline:
    def __init__(self):
        self.seen_ids = set()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        company_id = adapter.get("company_id")

        if company_id in self.seen_ids:
            raise DropItem(f"Duplicate company_id: {company_id}")

        self.seen_ids.add(company_id)
        return item