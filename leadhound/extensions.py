"""
Scrapy extension that saves the crawl's stats to a JSON file when the spider closes.

Why it exists: the weekly CI scrape needs to know *why* a run produced few or
no rows (did the site answer 403? did the HTML change?). Scrapy only prints
its stats into the log; a JSON file is easy for leadhound/quality.py to read.

It's switched on in settings.py (EXTENSIONS) but does nothing unless you give
it a path:
    scrapy crawl real_estate_agents -O output/leads.csv -s STATS_JSON_PATH=output/stats.json
"""

import json
from pathlib import Path

from scrapy import signals
from scrapy.exceptions import NotConfigured


class StatsToJson:
    def __init__(self, path, stats):
        self.path = Path(path)
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        path = crawler.settings.get("STATS_JSON_PATH")
        if not path:
            # Scrapy's way of saying "leave this extension off for this run".
            raise NotConfigured
        extension = cls(path, crawler.stats)
        crawler.signals.connect(extension.spider_closed, signal=signals.spider_closed)
        return extension

    def spider_closed(self, spider, reason):
        stats = dict(self.stats.get_stats())
        stats.setdefault("finish_reason", reason)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # default=str turns the start/finish datetimes into plain text.
        self.path.write_text(json.dumps(stats, indent=2, sort_keys=True, default=str), encoding="utf-8")
