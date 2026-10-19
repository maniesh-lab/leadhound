# leadhound

A production-style lead generation scraper built on Scrapy. Crawls business
directory listings, extracts structured contact data, validates and
deduplicates it through a custom item pipeline, and exports clean CSV — built
with the settings and error-handling a scraper needs to run unattended, not a
one-off script.

Built as the first project in a lead-gen automation pipeline (scraper → n8n
routing → lead scoring → CRM hookup).

---

## What it does

Scrapes real estate agent listings from [nepalyp.com](https://www.nepalyp.com)
(Nepal Business Directory) in Kathmandu. For each business, it
pulls company name, address, phone number, year established, "years with us,"
verification status, and rating/review data where available — then validates,
cleans, and deduplicates the results before writing them to CSV.

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
│   └── spiders/
│       ├── __init__.py
│       └── real_estate_agents.py   # the actual crawler
│
├── examples/
│   └── sample_output.csv           # trimmed sample of real scraped output
├── tests/
│   ├── test_pipelines.py           # validation, cleaning, dedup
│   └── test_spider.py              # parsing, pagination, Playwright switch
├── .github/workflows/ci.yml        # lint + tests on every push
├── pytest.ini
├── ruff.toml                       # lint rules
├── output/                         # gitignored — full scrape output lands here
├── .env.example
├── .gitignore
├── requirements.txt
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
playwright install chromium
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
pytest
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
| `itemadapter` | Uniform read/write access to item fields inside pipelines |
| Custom pipelines | Validation, data cleaning, deduplication |

---

## Known Limitations

Listed deliberately, not hidden — a scraper's boundaries matter as much as its features:

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
  crawl returns fewer fields. GitHub Actions runs them, plus a `ruff` lint
  check, on Python 3.10–3.13 for every push.
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

## Use Case

Built for anyone who needs a structured, exportable list of businesses in a
given category and region — the raw material a lead-generation or outreach
workflow runs on — without manually copying listings out of a directory page
by page.

---

## Author

**Manish Pandeya** · [github.com/maniesh-lab](https://github.com/maniesh-lab)