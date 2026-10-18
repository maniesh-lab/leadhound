"""
Unit tests for the three item pipelines. No network needed: each test
builds an item by hand and pushes it through one pipeline.
"""

import pytest
from scrapy.exceptions import DropItem

from leadhound.items import RealEstateAgentItem
from leadhound.pipelines import CleaningPipeline, DedupPipeline, ValidationPipeline


def make_item(**fields):
    item = RealEstateAgentItem()
    defaults = {
        "company_id": "1",
        "name": "Test Realty",
        "profile_url": "https://www.nepalyp.com/company/1/Test_Realty",
    }
    defaults.update(fields)
    for key, value in defaults.items():
        item[key] = value
    return item


# --- ValidationPipeline ---

def test_validation_keeps_complete_item():
    item = make_item()
    assert ValidationPipeline().process_item(item, spider=None) is item


@pytest.mark.parametrize("missing", ["name", "profile_url"])
def test_validation_drops_item_missing_required_field(missing):
    item = make_item(**{missing: None})
    with pytest.raises(DropItem):
        ValidationPipeline().process_item(item, spider=None)


def test_validation_allows_empty_optional_fields():
    item = make_item(tagline=None, rating=None)
    assert ValidationPipeline().process_item(item, spider=None) is item


# --- CleaningPipeline ---

def test_cleaning_fixes_address_spacing():
    item = make_item(address="Naxal ,   Kathmandu ,\n Nepal")
    CleaningPipeline().process_item(item, spider=None)
    assert item["address"] == "Naxal, Kathmandu, Nepal"


def test_cleaning_turns_review_text_into_number():
    item = make_item(review_count="3 Reviews")
    CleaningPipeline().process_item(item, spider=None)
    assert item["review_count"] == 3


def test_cleaning_review_text_without_digits_becomes_none():
    item = make_item(review_count="Reviews")
    CleaningPipeline().process_item(item, spider=None)
    assert item["review_count"] is None


def test_cleaning_turns_rating_into_float():
    item = make_item(rating="4.5")
    CleaningPipeline().process_item(item, spider=None)
    assert item["rating"] == 4.5


def test_cleaning_bad_rating_becomes_none():
    item = make_item(rating="n/a")
    CleaningPipeline().process_item(item, spider=None)
    assert item["rating"] is None


# --- DedupPipeline ---

def test_dedup_drops_repeat_company_id():
    pipeline = DedupPipeline()
    pipeline.process_item(make_item(company_id="42"), spider=None)
    with pytest.raises(DropItem):
        pipeline.process_item(make_item(company_id="42"), spider=None)


def test_dedup_keeps_different_company_ids():
    pipeline = DedupPipeline()
    pipeline.process_item(make_item(company_id="1"), spider=None)
    item = make_item(company_id="2")
    assert pipeline.process_item(item, spider=None) is item


def test_dedup_falls_back_to_profile_url_when_id_missing():
    # Two different listings with no company_id must both survive...
    pipeline = DedupPipeline()
    first = make_item(company_id=None, profile_url="https://example.com/a")
    second = make_item(company_id=None, profile_url="https://example.com/b")
    assert pipeline.process_item(first, spider=None) is first
    assert pipeline.process_item(second, spider=None) is second

    # ...but the same ID-less listing seen twice is still a duplicate.
    with pytest.raises(DropItem):
        pipeline.process_item(
            make_item(company_id=None, profile_url="https://example.com/a"), spider=None
        )
