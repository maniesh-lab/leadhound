"""
Tests for leadhound/quality.py, the data-quality checker the weekly scrape
workflow runs on the fresh CSV. Each test writes a tiny CSV to a temp folder,
so nothing touches the network or the real output/ folder.
"""

import csv
import json
from pathlib import Path

import pytest

from leadhound import quality

SAMPLE_CSV = Path(__file__).parent.parent / "examples" / "sample_output.csv"


def good_row(**changes):
    row = {
        "company_id": "65740",
        "name": "EXCOM GROUP (P) Ltd",
        "profile_url": "https://www.nepalyp.com/company/65740/EXCOM_GROUP_P_Ltd",
        "address": "Naxal, Kathmandu, Nepal",
        "tagline": "",
        "phone": "977-1-4416941/43",
        "established_year": "2017",
        "years_with_us": "+9",
        "verified": "True",
        "rating": "5.0",
        "review_count": "3",
        "source_url": "https://www.nepalyp.com/category/Estate_agents/city:Kathmandu",
        "scraped_at": "2026-09-09T11:32:09+00:00",
    }
    row.update(changes)
    return row


def write_csv(path, rows, columns=None):
    columns = columns or quality.EXPECTED_COLUMNS
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def checks_failed(report):
    return {p.check for p in report.problems}


# --- the committed sample must always pass ---

def test_sample_output_passes():
    report = quality.check_csv(str(SAMPLE_CSV), min_rows=20)
    assert report.problems == []
    assert report.status == "passed"


# --- one test per rule ---

def test_clean_file_passes(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row(), good_row(company_id="2", profile_url="https://x/2")])
    assert quality.check_csv(path).status == "passed"


def test_missing_required_field_fails(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row(name="")])
    report = quality.check_csv(path)
    assert report.status == "failed"
    assert report.problems[0].row == 2  # first data row is spreadsheet row 2
    assert "name is empty" in report.problems[0].message


def test_missing_column_fails(tmp_path):
    columns = [c for c in quality.EXPECTED_COLUMNS if c != "phone"]
    path = write_csv(tmp_path / "leads.csv", [good_row()], columns=columns)
    assert checks_failed(quality.check_csv(path)) == {"columns"}


def test_duplicate_listing_fails(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row(), good_row()])
    report = quality.check_csv(path)
    assert checks_failed(report) == {"duplicate"}
    assert report.problems[0].row == 3
    assert "row 2" in report.problems[0].message


def test_duplicate_falls_back_to_profile_url(tmp_path):
    rows = [good_row(company_id="", profile_url="https://x/a"), good_row(company_id="", profile_url="https://x/a")]
    path = write_csv(tmp_path / "leads.csv", rows)
    assert checks_failed(quality.check_csv(path)) == {"duplicate"}


def test_blank_optional_fields_are_fine(tmp_path):
    row = good_row(phone="", rating="", review_count="", established_year="", years_with_us="")
    path = write_csv(tmp_path / "leads.csv", [row])
    assert quality.check_csv(path).status == "passed"


def test_too_few_rows_fails(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row()])
    assert checks_failed(quality.check_csv(path, min_rows=100)) == {"row_count"}


def test_missing_file_counts_as_zero_rows(tmp_path):
    report = quality.check_csv(str(tmp_path / "nope.csv"))
    assert report.rows == 0
    assert checks_failed(report) == {"row_count"}


@pytest.mark.parametrize("phone", ["4480873", "00977-1-4262078", "977-1-4416941/43", "+977 9841234567"])
def test_real_phone_shapes_pass(phone):
    assert quality.phone_problem(phone) is None


@pytest.mark.parametrize("phone", ["call us", "98-41", "977-1-44169x1"])
def test_bad_phones_fail(phone):
    assert quality.phone_problem(phone) is not None


@pytest.mark.parametrize("rating", ["5.6", "-1", "great"])
def test_bad_rating_fails(rating):
    assert quality.rating_problem(rating) is not None


@pytest.mark.parametrize("value", ["3.5", "3 Reviews", "-2"])
def test_bad_review_count_fails(value):
    assert quality.review_count_problem(value) is not None


@pytest.mark.parametrize("year", ["1850", "3000", "Established 2017"])
def test_bad_established_year_fails(year):
    assert quality.established_year_problem(year) is not None


def test_verified_must_be_true_or_false(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row(verified="yes")])
    assert checks_failed(quality.check_csv(path)) == {"verified"}


# --- fill rates ---

def test_fill_rates(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row(), good_row(company_id="2", phone="")])
    rates = quality.check_csv(path).fill_rates
    assert rates["phone"] == 0.5
    assert rates["rating"] == 1.0


# --- blocked vs broken ---

def test_zero_rows_with_403_is_blocked_not_failed(tmp_path):
    stats = {"downloader/response_status_count/403": 2, "item_scraped_count": 0}
    report = quality.check_csv(str(tmp_path / "empty.csv"), min_rows=100, stats=stats)
    assert report.status == "blocked"
    assert report.blocked_reason == "HTTP 403 x2"


def test_zero_rows_with_network_error_is_blocked(tmp_path):
    stats = {"downloader/exception_type_count/twisted.internet.error.TCPTimedOutError": 4}
    report = quality.check_csv(str(tmp_path / "empty.csv"), stats=stats)
    assert report.blocked_reason == "TCPTimedOutError x4"


def test_zero_rows_with_only_200s_is_a_real_failure(tmp_path):
    # The site answered fine but we parsed nothing: the HTML changed. That must fail.
    stats = {"downloader/response_status_count/200": 8}
    report = quality.check_csv(str(tmp_path / "empty.csv"), stats=stats)
    assert report.status == "failed"


def test_some_rows_plus_a_403_is_not_blocked(tmp_path):
    path = write_csv(tmp_path / "leads.csv", [good_row()])
    stats = {"downloader/response_status_count/403": 1}
    assert quality.check_csv(path, stats=stats).blocked_reason is None


# --- command line + summary ---

def test_cli_exit_codes_and_summary_file(tmp_path):
    good = write_csv(tmp_path / "good.csv", [good_row()])
    bad = write_csv(tmp_path / "bad.csv", [good_row(rating="9")])
    summary = tmp_path / "summary.md"

    assert quality.main([good, "--summary", str(summary)]) == 0
    assert quality.main([bad, "--summary", str(summary)]) == 1

    text = summary.read_text(encoding="utf-8")
    assert "✅ PASSED" in text
    assert "❌ FAILED" in text
    assert "row 2 · rating: rating 9.0 is outside 0-5" in text


def test_cli_blocked_run_exits_zero_with_warning(tmp_path, capsys):
    stats_file = tmp_path / "stats.json"
    stats_file.write_text(json.dumps({"downloader/response_status_count/403": 1, "finish_reason": "finished"}))
    code = quality.main([str(tmp_path / "empty.csv"), "--min-rows", "100", "--stats", str(stats_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "⚠️ BLOCKED" in out
    assert "::warning::" in out
    assert "| Finish reason | finished |" in out
