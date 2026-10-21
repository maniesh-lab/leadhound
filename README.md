# leadhound

[![CI](https://github.com/maniesh-lab/leadhound/actions/workflows/ci.yml/badge.svg)](https://github.com/maniesh-lab/leadhound/actions/workflows/ci.yml)
[![Scrape](https://github.com/maniesh-lab/leadhound/actions/workflows/scrape.yml/badge.svg)](https://github.com/maniesh-lab/leadhound/actions/workflows/scrape.yml)

A Scrapy scraper that collects real estate agent listings in Kathmandu from
one Nepal business directory ([nepalyp.com](https://www.nepalyp.com)) and walks
every results page. For each listing it saves the company name, address, phone
number, year established, "years with us", verification status and
rating/review data where available, then validates, cleans and deduplicates the
listings before writing a CSV. It obeys robots.txt, slows itself down to be polite, retries
failed pages, and logs every run to a file. An optional Playwright mode is
there for sites that build their pages with JavaScript.

It's the first stage of my lead-gen pipeline: leadhound scrapes the leads,
[Switchyard](https://github.com/maniesh-lab/Switchyard) cleans, dedupes,
scores and stores them in Airtable, and an AI scoring step is planned next.

---

## Features

- Full pagination — walks every results page automatically, not just the first
- Item pipeline with three stages: validation (drops rows missing a name or
  profile URL), cleaning (fixes address formatting, converts rating/review
  text into real numbers), and deduplication (by the site's own internal
  company ID, falling back to the profile URL when a listing has no ID)
- Optional Playwright rendering — one flag (`-a use_playwright=true`) sends
  every request through headless Chromium for sites that build their
  listings with JavaScript; off by default, so static sites stay fast
- Unit tests for every pipeline stage and for the spider's parsing,
  pagination, and Playwright switch — no network needed to run them
- robots.txt respected (`ROBOTSTXT_OBEY = True`) — not a bypassable setting
- AutoThrottle + manual delay + retry-on-failure settings, tuned for
  politeness over raw speed
- Structured logging to a file (`leadhound.log`) — every run's fetches, drops,
  and errors are traceable after the fact, not just visible in a terminal that
  closes
- Realistic browser User-Agent — plain Scrapy identifies itself as a bot by
  default; this doesn't

---

## Project Structure

```
leadhound/
│
├── leadhound/
│   ├── __init__.py
│   ├── items.py                    # RealEstateAgentItem schema
│   ├── pipelines.py                # ValidationPipeline, CleaningPipeline, DedupPipeline
│   ├── middlewares.py              # unmodified Scrapy defaults — no custom need yet
│   ├── settings.py                 # throttling, retries, logging, robots.txt, UA, Playwright
│   ├── playwright_utils.py         # builds request meta for Playwright-rendered pages
│   ├── quality.py                  # data-quality checks for the output CSV
│   ├── extensions.py               # saves crawl stats to JSON (used by the weekly scrape)
│   └── spiders/
│       ├── __init__.py
│       └── real_estate_agents.py   # the actual crawler
│
├── examples/
│   └── sample_output.csv           # trimmed sample of real scraped output
├── tests/
│   ├── conftest.py                 # writes a pass/fail table to the GitHub run page
│   ├── test_pipelines.py           # validation, cleaning, dedup
│   ├── test_spider.py              # parsing, pagination, Playwright switch
│   ├── test_quality.py             # data-quality checker
│   └── test_extensions.py          # crawl-stats JSON
├── .github/workflows/
│   ├── ci.yml                      # lint + tests on every push
│   └── scrape.yml                  # weekly live scrape + data-quality check
├── constraints.txt                 # exact versions for the weekly scrape
├── pytest.ini
├── ruff.toml                       # lint rules
├── output/                         # gitignored — full scrape output lands here
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-test.txt           # + pytest and ruff for tests and lint
├── LICENSE
├── scrapy.cfg
└── README.md
```

---

## How It Works

1. **Fetch** — the spider requests the listing page, identifying itself with a
   real browser User-Agent. With `use_playwright=true`, the page is opened in
   headless Chromium instead, and the spider waits for the listings to appear
   before reading the HTML
2. **Parse** — each business's HTML block is walked individually; name,
   address, phone, and metadata are pulled out via CSS selectors, with XPath
   used specifically where a field needs to be matched by its icon's
   `aria-label` (e.g. distinguishing the phone number from the "established"
   date, since both sit in visually similar rows)
3. **Paginate** — the spider follows the page's `rel="next"` link and repeats
   step 2, until there's no next page left
4. **Validate** — any item missing a name or profile URL is dropped outright;
   everything else is allowed through even if optional fields (tagline,
   rating) are empty, since real listings frequently omit them
5. **Clean** — address strings are normalized (stray whitespace from nested
   HTML tags removed), and review/rating fields are converted from text
   (`"3 Reviews"`) into real numbers (`3`)
6. **Deduplicate** — each business's site-assigned ID (or its profile URL, if
   the ID is missing) is tracked in-memory for the run; repeats are dropped
7. **Export** — surviving items are written to CSV

---

## How to Run

**1. Clone the repo**
```bash
git clone https://github.com/maniesh-lab/leadhound
cd leadhound
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
playwright install chromium   # only needed for the optional Playwright mode
```

**4. Run the spider**
```bash
scrapy crawl real_estate_agents -O output/leads.csv
```

Output lands in `output/leads.csv`. A run log is written to `leadhound.log` in
the project root.

**Optional: render pages with Playwright**

For a target that loads its listings with JavaScript, add one flag:
```bash
scrapy crawl real_estate_agents -a use_playwright=true -O output/leads.csv
```
nepalyp.com doesn't need it (it sends plain HTML), so it's off by default.

**5. Run the tests**
```bash
pip install -r requirements.txt -r requirements-test.txt
pytest
ruff check .
```

GitHub Actions runs the same tests and lint check on Python 3.10–3.13 for every push.

---

## How CI Works

Two GitHub Actions workflows:

- **CI** (`ci.yml`): on every push and pull request, runs the ruff lint and
  every test on Python 3.10–3.13. Tests never touch the network. If a test
  fails, the run's summary page lists each failing test and why.
- **Scrape** (`scrape.yml`): every Monday, or on demand from the Actions tab.
  It runs the tests, scrapes the live site (capped at 20 pages), then checks
  the CSV with `leadhound/quality.py`:
  - all columns are present and there are at least 100 rows
  - name, profile URL, source URL and timestamp are filled on every row
  - there are no duplicate listings
  - phone, rating (0–5), review count and established year look right

  The CSV, the crawl stats and the log are uploaded as a downloadable
  artifact. The run page shows a pass/fail table and how full each column is.

If the site blocks GitHub's servers (common for scrapers on cloud IPs), the
run stays green with a "blocked" warning, and the tests remain the gate. If
the scrape works but the data is bad, the run fails.

You can run the same check on your own output:
```bash
scrapy crawl real_estate_agents -O output/leads.csv -s STATS_JSON_PATH=output/stats.json
python -m leadhound.quality output/leads.csv --min-rows 100 --stats output/stats.json
```

---

## Example Output

```csv
company_id,name,profile_url,address,tagline,phone,established_year,years_with_us,verified,rating,review_count,source_url,scraped_at
65740,EXCOM GROUP (P) Ltd,https://www.nepalyp.com/company/65740/EXCOM_GROUP_P_Ltd,"Sixth Floor, Four Square Complex, Naxal, Kathmandu, Nepal",Connecting buyers and sellers for real estate success.,977-1-4416941/43,2017,+9,True,5.0,3,https://www.nepalyp.com/category/Estate_agents/city:Kathmandu,2026-09-09T11:32:09.149057+00:00
```

See `examples/sample_output.csv` for a fuller sample.

---

## Tech Stack

| Tool | Purpose |
|---|---|
| `scrapy` | Crawling engine, pagination, item pipelines |
| `scrapy-playwright` | Optional headless-Chromium rendering for JavaScript-heavy targets (`-a use_playwright=true`) |
| `pytest` | Unit tests for pipelines and spider parsing |
| `ruff` | Lint check, run with the tests by GitHub Actions on every push |
| `itemadapter` | Uniform read/write access to item fields inside pipelines |
| Custom pipelines | Validation, data cleaning, deduplication |

---

## Use Case

Built for anyone who needs a structured, exportable list of businesses in a
given category and region — the raw material a lead-generation or outreach
workflow runs on — without manually copying listings out of a directory page
by page.

---

## Known Limitations

- **No CAPTCHA solving, proxy rotation, or distributed crawling.** This is a
  single-machine, directory-scale scraper, not built to fight enterprise-grade
  bot protection. During development it was tested against Clutch.co, a
  much larger B2B directory, and was blocked outright by Cloudflare's managed
  challenge. That's treated as an intentional scope boundary, not a bug —
  reliably defeating that kind of protection requires paid
  proxy/unlocker infrastructure, which is a different project with a
  different cost profile.
- **Playwright mode isn't exercised by the current target.** nepalyp.com
  serves fully static HTML end to end — confirmed by comparing raw `curl`
  output against what Scrapy receives — so the default run never opens a
  browser. Playwright mode is tested against a local JavaScript-rendered
  page, not against a live JS-heavy directory.
- **Selectors are hardcoded in the spider**, not externalized to a config
  file. A config-driven design (selectors defined per-target in an external
  file, spider reads from it) was part of the original plan and would make
  retargeting to a new site faster — it's a planned refactor, not yet done.
- **Deduplication is per-run only.** The dedup pipeline tracks seen company
  IDs in memory for the duration of one crawl; it doesn't persist across
  separate runs. Running the spider twice on two different days won't detect
  that a business was already scraped last time.
- **Tests use a hand-written HTML page, not a saved copy of the live site.**
  They prove the parsing logic works on the structure the selectors expect;
  if nepalyp.com changes its HTML, the tests will still pass while a live
  crawl returns fewer fields.
- **Some fields are legitimately sparse.** Not every listing on the source
  site has a tagline, a rating, or a "years with us" badge. Rather than force
  these to always exist, the schema treats them as optional — meaning a
  clean CSV can still have blank cells for these columns, by design.

---

## Legal / Ethical Notes

- `ROBOTSTXT_OBEY = True` is set and enforced — any path the target site
  disallows in its `robots.txt` is never fetched
- The target data is public business directory information (name, address,
  phone) that businesses list specifically to be found — not scraped from
  behind a login or paywall
- Email addresses on the source site are gated behind a sign-in wall and are
  deliberately **not** scraped — working around an authentication gate was
  treated as out of scope, not a technical limitation to solve around

---

## Author

**Manish Pandeya** · [github.com/maniesh-lab](https://github.com/maniesh-lab)
