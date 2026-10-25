"""
Shared pytest setup.

When the tests run on GitHub Actions, this writes a short pass/fail table to
the run's summary page, so a failure can be read without digging through the
raw log. GitHub sets the GITHUB_STEP_SUMMARY env var; locally it isn't set,
so this does nothing.
"""

import os
import platform

MAX_REASON_LENGTH = 200


def short_reason(report):
    """One line saying why a test failed, e.g. "AssertionError: assert 1 == 2"."""
    crash = getattr(report.longrepr, "reprcrash", None)
    text = crash.message if crash else str(report.longrepr).strip().splitlines()[-1]
    text = " ".join(text.split()).replace("|", "\\|")  # one line, safe inside a table
    return text[:MAX_REASON_LENGTH]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    skipped = len(stats.get("skipped", []))
    failed = stats.get("failed", []) + stats.get("error", [])

    headline = "✅ all passed" if not failed else f"❌ {len(failed)} failed"
    lines = [
        f"## Tests on Python {platform.python_version()}: {headline}",
        "",
        f"{passed} passed · {len(failed)} failed · {skipped} skipped",
        "",
    ]
    if failed:
        lines += ["| Test | Why it failed |", "|---|---|"]
        lines += [f"| `{report.nodeid}` | {short_reason(report)} |" for report in failed]
        lines.append("")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
