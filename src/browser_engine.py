import os
import time
import random
import logging
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_sync

logger = logging.getLogger("MarianoScraper.BrowserEngine")

class BrowserEngine:
    """
    Manages Playwright browser instances, anti-detect stealth capabilities,
    store location context selection, and fulfillment state verification for Mariano's.
    """

    def __init__(self, settings: Dict[str, Any], proxy_config: Optional[Dict[str, Any]] = None):
        self.settings = settings.get("scraping", {})
        self.proxy_config = proxy_config or {}
        self.headless = self.settings.get("headless", True)
        self.page_timeout = self.settings.get("page_timeout_ms", 45000)
        self.min_delay = self.settings.get("request_delay_min_seconds", 2.0)
        self.max_delay = self.settings.get("request_delay_max_seconds", 4.5)

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def start(self) -> None:
        """Starts Playwright and initializes browser context with stealth."""
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certifcate-errors",
            "--ignore-certifcate-errors-spki-list",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ]

        proxy_args = None
        if self.proxy_config.get("enabled"):
            server = self.proxy_config.get("http_proxy") or self.proxy_config.get("https_proxy")
            if server:
                proxy_args = {"server": server}
                logger.info(f"Using proxy: {server.split('@')[-1] if '@' in server else server}")

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
            proxy=proxy_args
        )

        self._context = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/Chicago"
        )

    def set_store_location(self, location: Dict[str, Any]) -> None:
        """
        Configures store and fulfillment context (Store ID, ZIP code, Pickup intent)
        in browser cookies and local storage so that Mariano's in-store pricing is loaded.
        """
        if not self._context:
            return

        zipcode = str(location.get("zipcode", "60601"))
        store_id = str(location.get("store_id", "531"))
        
        # Inject standard Mariano's / Kroger store context cookies
        cookies = [
            {"name": "postalCode", "value": zipcode, "domain": ".marianos.com", "path": "/"},
            {"name": "kroger.postalCode", "value": zipcode, "domain": ".marianos.com", "path": "/"},
            {"name": "kroger.storeId", "value": store_id, "domain": ".marianos.com", "path": "/"},
            {"name": "storeIntent", "value": "PICKUP", "domain": ".marianos.com", "path": "/"},
            {
                "name": "kroger.modality",
                "value": f'{{"intent":"PICKUP","postalCode":"{zipcode}","divisionNumber":"531","storeNumber":"{store_id}"}}',
                "domain": ".marianos.com",
                "path": "/"
            }
        ]
        try:
            self._context.add_cookies(cookies)
            logger.info(f"Mariano's store context verified: ZIP={zipcode}, StoreID={store_id}, Intent=PICKUP")
        except Exception as e:
            logger.warning(f"Failed to set store context cookies: {e}")

    def fetch_page_content(self, url: str) -> str:
        """
        Navigates to URL using Playwright stealth, waits for dynamic content,
        and returns rendered HTML.
        """
        if not self._context:
            self.start()

        # Controlled pacing delay
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

        page: Page = self._context.new_page()
        stealth_sync(page)

        try:
            logger.info(f"Navigating to {url} (pacing delay: {delay:.2f}s)")
            page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout)

            # Scroll slightly to trigger lazy-loading of product cards
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.0)

            content = page.content()
            return content
        finally:
            page.close()

    def close(self) -> None:
        """Closes browser and Playwright process cleanly."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser engine: {e}")
        finally:
            self._context = None
            self._browser = None
            self._playwright = None
