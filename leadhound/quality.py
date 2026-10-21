"""
Data-quality checks for a leadhound output CSV.

Why it exists: a crawl can "succeed" while the site has changed its HTML,
leaving a CSV that is empty, half-filled or full of junk. These checks catch
that, and say *why* in plain words.

Who calls it:
- the weekly scrape workflow (.github/workflows/scrape.yml), on the fresh CSV
- tests/test_quality.py, on small hand-made rows and on examples/sample_output.csv

Run it by hand:
    python -m leadhound.quality output/leads.csv --min-rows 100 --stats output/stats.json

Exit code: 0 = passed (or the site blocked us, see blocked_reason), 1 = failed.
"""

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from leadhound.items import RealEstateAgentItem

# Every column the spider can write. Taken from the item, so there's one source of truth.
EXPECTED_COLUMNS = list(RealEstateAgentItem.fields)

# Fields every row must have. Same as ValidationPipeline, plus the two the spider always sets.
REQUIRED_FIELDS = ("name", "profile_url", "source_url", "scraped_at")

# Optional fields: allowed to be blank, but we report how full they are.
OPTIONAL_FIELDS = ("company_id", "address", "tagline", "phone", "established_year",
                   "years_with_us", "rating", "review_count")

# Nepali numbers come in many shapes: "4480873", "00977-1-4262078", "977-1-4416941/43".
# So we only check the characters used and that there are enough digits.
PHONE_CHARS = re.compile(r"[0-9+\-/(), ]+")
MIN_PHONE_DIGITS = 6

# HTTP codes that usually mean "the site doesn't want this visitor".
BLOCK_STATUS_CODES = ("403", "429", "503")

# Every check, in the order the summary shows them.
CHECKS = {
    "columns": "All expected columns present",
    "row_count": "Enough rows",
    "required": "Required fields filled (" + ", ".join(REQUIRED_FIELDS) + ")",
    "duplicate": "No duplicate listings (by company_id, else profile_url)",
    "phone": "Phone looks like a phone number",
    "rating": "Rating is a number from 0 to 5",
    "review_count": "Review count is a whole number, 0 or more",
    "established_year": "Established year is between 1900 and this year",
    "verified": "Verified is True or False",
}

MAX_PROBLEMS_SHOWN = 30


@dataclass
class Problem:
    check: str           # a key from CHECKS
    message: str
    row: int | None = None  # spreadsheet row number (header is row 1); None = whole file


@dataclass
class Report:
    path: str
    rows: int
    min_rows: int
    problems: list[Problem]
    fill_rates: dict[str, float]
    blocked_reason: str | None = None

    @property
    def status(self) -> str:
        """'blocked', 'failed' or 'passed'."""
        if self.blocked_reason:
            return "blocked"
        return "failed" if self.problems else "passed"


# --- reading ---------------------------------------------------------------

def read_csv(path: str) -> tuple[list[str], list[dict]]:
    """Return (column names, rows). A missing or empty file gives ([], [])."""
    file = Path(path)
    if not file.exists() or file.stat().st_size == 0:
        return [], []
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def load_stats(path: str) -> dict | None:
    """Read the crawl stats JSON written by leadhound.extensions.StatsToJson."""
    file = Path(path)
    if not file.exists():
        return None
    return json.loads(file.read_text(encoding="utf-8"))


# --- single-value checks: each returns a problem message, or None if fine ----

def phone_problem(value: str) -> str | None:
    if not PHONE_CHARS.fullmatch(value):
        return f"unexpected characters in phone {value!r}"
    digits = sum(ch.isdigit() for ch in value)
    if digits < MIN_PHONE_DIGITS:
        return f"phone {value!r} has only {digits} digits"
    return None


def rating_problem(value: str) -> str | None:
    try:
        rating = float(value)
    except ValueError:
        return f"rating {value!r} is not a number"
    if not 0 <= rating <= 5:
        return f"rating {rating} is outside 0-5"
    return None


def review_count_problem(value: str) -> str | None:
    if not value.isdigit():
        return f"review count {value!r} is not a whole number"
    return None


def established_year_problem(value: str) -> str | None:
    this_year = date.today().year
    if not value.isdigit() or not 1900 <= int(value) <= this_year:
        return f"established year {value!r} is not between 1900 and {this_year}"
    return None


# Optional fields with a format rule. Blank values are skipped.
VALUE_CHECKS = {
    "phone": phone_problem,
    "rating": rating_problem,
    "review_count": review_count_problem,
    "established_year": established_year_problem,
}


# --- row and file checks -----------------------------------------------------

def check_columns(columns: list[str]) -> list[Problem]:
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    if missing:
        return [Problem("columns", "missing column(s): " + ", ".join(missing))]
    return []


def check_row(row_number: int, row: dict) -> list[Problem]:
    problems = []

    for field in REQUIRED_FIELDS:
        if not (row.get(field) or "").strip():
            problems.append(Problem("required", f"{field} is empty", row_number))

    for field, check in VALUE_CHECKS.items():
        value = (row.get(field) or "").strip()
        if value:
            message = check(value)
            if message:
                problems.append(Problem(field, message, row_number))

    # The spider always sets verified to a real True/False, so blank is a problem too.
    if row.get("verified") not in ("True", "False"):
        problems.append(Problem("verified", f"verified is {row.get('verified')!r}", row_number))

    return problems


def check_duplicates(rows: list[dict]) -> list[Problem]:
    """Same key rule as DedupPipeline: company_id, falling back to profile_url."""
    first_seen: dict[str, int] = {}
    problems = []
    for row_number, row in enumerate(rows, start=2):
        key = row.get("company_id") or row.get("profile_url")
        if not key:
            continue  # check_row already reports the missing profile_url
        if key in first_seen:
            problems.append(Problem("duplicate", f"same listing as row {first_seen[key]} ({key})", row_number))
        else:
            first_seen[key] = row_number
    return problems


def fill_rates(rows: list[dict]) -> dict[str, float]:
    """Share of rows (0.0-1.0) where each optional field is not blank."""
    if not rows:
        return {}
    return {
        field: sum(1 for row in rows if (row.get(field) or "").strip()) / len(rows)
        for field in OPTIONAL_FIELDS
    }


def blocked_reason(stats: dict | None, row_count: int) -> str | None:
    """If the crawl got zero rows *and* the site refused us, say how. Else None.

    Zero rows with only normal (200) answers is NOT "blocked": it means the
    HTML changed, and that should fail the run.
    """
    if not stats or row_count > 0:
        return None
    reasons = []
    for code in BLOCK_STATUS_CODES:
        count = stats.get(f"downloader/response_status_count/{code}", 0)
        if count:
            reasons.append(f"HTTP {code} x{count}")
    for key, count in stats.items():
        if key.startswith("downloader/exception_type_count/"):
            error_name = key.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            reasons.append(f"{error_name} x{count}")
    return ", ".join(reasons) or None


def check_csv(path: str, min_rows: int = 1, stats: dict | None = None) -> Report:
    """Run every check on one CSV file and return a Report."""
    columns, rows = read_csv(path)
    problems = []

    if len(rows) < min_rows:
        problems.append(Problem("row_count", f"got {len(rows)} rows, need at least {min_rows}"))
    if rows:
        problems += check_columns(columns)
    for row_number, row in enumerate(rows, start=2):
        problems += check_row(row_number, row)
    problems += check_duplicates(rows)

    return Report(
        path=path,
        rows=len(rows),
        min_rows=min_rows,
        problems=problems,
        fill_rates=fill_rates(rows),
        blocked_reason=blocked_reason(stats, len(rows)),
    )


# --- summary -----------------------------------------------------------------

HEADLINES = {
    "passed": "✅ PASSED",
    "failed": "❌ FAILED",
    "blocked": "⚠️ BLOCKED (the site refused the request)",
}


def format_summary(report: Report, stats: dict | None = None) -> str:
    """Markdown summary for GitHub's job summary page (and the terminal)."""
    lines = [
        f"## Data-quality check: {HEADLINES[report.status]}",
        "",
        f"**File:** `{report.path}` · **Rows:** {report.rows} (need at least {report.min_rows})",
        "",
    ]

    if report.status == "blocked":
        lines += [
            f"The live site refused the scraper ({report.blocked_reason}). This is usually the site "
            "blocking GitHub's servers, not a bug in leadhound. The fixture tests are still the gate, "
            "so this run does not fail.",
            "",
        ]

    lines += ["| Check | Result |", "|---|---|"]
    for key, label in CHECKS.items():
        count = sum(1 for p in report.problems if p.check == key)
        lines.append(f"| {label} | {'✅' if count == 0 else f'❌ {count} problem(s)'} |")
    lines.append("")

    if report.problems:
        lines += ["### Problems", ""]
        for p in report.problems[:MAX_PROBLEMS_SHOWN]:
            where = f"row {p.row}" if p.row else "file"
            lines.append(f"- {where} · {p.check}: {p.message}")
        hidden = len(report.problems) - MAX_PROBLEMS_SHOWN
        if hidden > 0:
            lines.append(f"- ...and {hidden} more")
        lines.append("")

    if report.fill_rates:
        lines += ["### How full each optional column is", "", "| Column | Filled |", "|---|---|"]
        for field, rate in report.fill_rates.items():
            lines.append(f"| {field} | {rate:.0%} |")
        lines.append("")

    if stats:
        lines += crawl_stats_lines(stats)

    return "\n".join(lines)


def crawl_stats_lines(stats: dict) -> list[str]:
    """A small table of the crawl numbers that matter, from Scrapy's stats."""
    status_counts = {
        key.rsplit("/", 1)[-1]: count
        for key, count in stats.items()
        if key.startswith("downloader/response_status_count/")
    }
    rows = [
        ("Finish reason", stats.get("finish_reason", "unknown")),
        ("Responses by HTTP code", ", ".join(f"{code}: {n}" for code, n in sorted(status_counts.items())) or "none"),
        ("Items scraped", stats.get("item_scraped_count", 0)),
        ("Items dropped by pipelines", stats.get("item_dropped_count", 0)),
    ]
    lines = ["### Crawl stats", "", "| Stat | Value |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    lines.append("")
    return lines


# --- command line --------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a leadhound output CSV.")
    parser.add_argument("csv_path", help="the CSV the spider wrote")
    parser.add_argument("--min-rows", type=int, default=1, help="fail if there are fewer rows (default 1)")
    parser.add_argument("--stats", help="crawl stats JSON from STATS_JSON_PATH, used to spot a blocked run")
    parser.add_argument("--summary", help="append the markdown summary to this file ($GITHUB_STEP_SUMMARY in CI)")
    args = parser.parse_args(argv)

    stats = load_stats(args.stats) if args.stats else None
    report = check_csv(args.csv_path, min_rows=args.min_rows, stats=stats)
    summary = format_summary(report, stats)

    print(summary)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(summary + "\n")

    if report.status == "blocked":
        # Shows up as a yellow warning on the GitHub run page.
        print(f"::warning::Live scrape looks blocked: {report.blocked_reason}")
        return 0
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
