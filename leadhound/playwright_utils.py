"""
Helpers for sending a request through Playwright (headless Chromium)
instead of Scrapy's normal downloader.

Only needed for sites that build their listings with JavaScript. The
current target (nepalyp.com) sends plain HTML, so the spider leaves this
off unless you pass -a use_playwright=true.
"""

from scrapy_playwright.page import PageMethod


def playwright_meta(wait_for_selector=None):
    """Build the request meta that tells scrapy-playwright to render a page.

    wait_for_selector: optional CSS selector. The browser waits until an
        element matching it appears, so the HTML handed back to the spider
        already contains the listings the JavaScript loaded.
    """
    meta = {"playwright": True}
    if wait_for_selector:
        meta["playwright_page_methods"] = [
            PageMethod("wait_for_selector", wait_for_selector),
        ]
    return meta
