import re
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class ValidationPipeline:
    def process_item(self, item, spider=None):
        adapter = ItemAdapter(item)
        if not adapter.get("name") or not adapter.get("profile_url"):
            raise DropItem(f"Missing required field(s) in: {dict(adapter)}")
        return item


class CleaningPipeline:
    def process_item(self, item, spider=None):
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

    def process_item(self, item, spider=None):
        adapter = ItemAdapter(item)
        # Prefer the site's own company ID. If a listing has none, fall back
        # to its profile URL (always present, ValidationPipeline checks it),
        # so ID-less listings aren't all treated as duplicates of "None".
        key = adapter.get("company_id") or adapter.get("profile_url")

        if key in self.seen_ids:
            raise DropItem(f"Duplicate listing: {key}")

        self.seen_ids.add(key)
        return item