"""
Tests for leadhound/extensions.py (StatsToJson). Uses Scrapy's own test
crawler, so no real crawl and no network.
"""

import json

import pytest
from scrapy.exceptions import NotConfigured
from scrapy.utils.test import get_crawler

from leadhound.extensions import StatsToJson


def test_off_when_no_path_given():
    with pytest.raises(NotConfigured):
        StatsToJson.from_crawler(get_crawler())


def test_writes_stats_json_on_close(tmp_path):
    path = tmp_path / "out" / "stats.json"
    crawler = get_crawler(settings_dict={"STATS_JSON_PATH": str(path)})
    extension = StatsToJson.from_crawler(crawler)

    crawler.stats.set_value("item_scraped_count", 142)
    crawler.stats.set_value("downloader/response_status_count/200", 8)
    extension.spider_closed(spider=None, reason="finished")

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["item_scraped_count"] == 142
    assert saved["downloader/response_status_count/200"] == 8
    assert saved["finish_reason"] == "finished"
