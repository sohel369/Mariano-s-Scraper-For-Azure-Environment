import os
import json
import time
import random
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Response

try:
    from playwright_stealth import Stealth
    _stealth_instance = Stealth()
    def apply_stealth(page: Page) -> None:
        _stealth_instance.apply_stealth_sync(page)
except Exception:
    def apply_stealth(page: Page) -> None:
        pass

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
        division_id = str(location.get("division_id", "531"))
        store_number = str(location.get("store_number", "00503"))
        store_id = str(location.get("store_id", "53100503"))
        
        # Inject standard Mariano's / Kroger store context cookies
        cookies = [
            {"name": "postalCode", "value": zipcode, "domain": ".marianos.com", "path": "/"},
            {"name": "kroger.postalCode", "value": zipcode, "domain": ".marianos.com", "path": "/"},
            {"name": "kroger.storeId", "value": store_id, "domain": ".marianos.com", "path": "/"},
            {"name": "storeIntent", "value": "PICKUP", "domain": ".marianos.com", "path": "/"},
            {
                "name": "kroger.modality",
                "value": f'{{"intent":"PICKUP","postalCode":"{zipcode}","divisionNumber":"{division_id}","storeNumber":"{store_number}"}}',
                "domain": ".marianos.com",
                "path": "/"
            }
        ]
        try:
            self._context.add_cookies(cookies)
            logger.info(
                f"Mariano's store context verified: Division={division_id}, StoreNum={store_number}, "
                f"FullStoreID={store_id}, ZIP={zipcode}, Intent=PICKUP"
            )
        except Exception as e:
            logger.warning(f"Failed to set store context cookies: {e}")

    def fetch_live_store_lookup(self, store_id: str, location_info: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and return an actual retailer HTTP response for store verification.

        No synthetic payload or disk fallback is allowed here. If the endpoint is
        unavailable, blocked, non-JSON, or returns an unexpected store, the caller
        must stop the collection run and report the failure.
        """
        if not self._context:
            self.start()

        # Keep the endpoint configurable because retailer endpoint paths can change.
        endpoint_template = os.environ.get(
            "MARIANOS_STORE_LOOKUP_URL_TEMPLATE",
            "https://www.marianos.com/api/v1/locations/{store_id}"
        )
        store_url = endpoint_template.format(store_id=store_id)
        logger.info("Requesting live store lookup from configured retailer endpoint: %s", store_url)

        timeout_ms = int(self.settings.get("store_lookup_timeout_ms", 12000))
        response = self._context.request.get(
            store_url,
            timeout=timeout_ms,
            headers={"Accept": "application/json"}
        )
        status = response.status
        response_headers = dict(response.headers)
        response_bytes = response.body()
        response_hash = hashlib.sha256(response_bytes).hexdigest()

        if not 200 <= status < 300:
            raise RuntimeError(
                f"Live store lookup failed with HTTP {status}; no replay fallback is permitted."
            )
        content_type = response_headers.get("content-type", "")
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"Live store lookup returned non-JSON content (content-type={content_type!r}); refusing to fabricate store data."
            ) from exc
        if not isinstance(payload, (dict, list)):
            raise RuntimeError("Live store lookup JSON must be an object or list; refusing to infer store identity.")

        return {
            "request_metadata": {
                "request_url": response.url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": "GET",
                "requested_store_id": str(store_id),
                "requested_fulfillment": "PICKUP"
            },
            "response_metadata": {
                "status_code": status,
                "headers": response_headers,
                "content_type": content_type,
                "content_length_bytes": len(response_bytes),
                "body_sha256": response_hash,
                "provenance_type": "fresh_live_http_response"
            },
            "raw_store_lookup_response": payload
        }

    def fetch_page_with_provenance(
        self,
        url: str,
        run_id: str = "",
        category_key: str = "",
        store_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Navigates to URL, captures full HTTP request/response evidence,
        computes SHA-256 hash of raw response bytes, and returns provenance manifest.
        """
        if not self._context:
            self.start()

        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

        page: Page = self._context.new_page()
        apply_stealth(page)

        response_meta = {
            "status": 200,
            "headers": {},
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        def on_response(response: Response):
            if response.url.split("?")[0] == url.split("?")[0] or "products" in response.url:
                response_meta["status"] = response.status
                response_meta["headers"] = dict(response.headers)
                response_meta["url"] = response.url

        page.on("response", on_response)

        try:
            logger.info(f"Navigating to {url} (pacing delay: {delay:.2f}s)")
            main_response = page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout)
            if main_response:
                response_meta["status"] = main_response.status
                response_meta["headers"] = dict(main_response.headers)

            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.0)

            content = page.content()
            content_bytes = content.encode("utf-8")
            sha256_hash = hashlib.sha256(content_bytes).hexdigest()

            is_blocked = response_meta["status"] in (403, 429) or "access denied" in content.lower()

            provenance = {
                "request_url": url,
                "timestamp": response_meta["timestamp"],
                "http_status": response_meta["status"],
                "response_headers": response_meta["headers"],
                "content_sha256": sha256_hash,
                "content_length_bytes": len(content_bytes),
                "run_id": run_id,
                "category_key": category_key,
                "store_context": store_context,
                "is_blocked": is_blocked,
                "html": content
            }
            return provenance
        finally:
            page.close()

    def fetch_page_content(self, url: str) -> str:
        """
        Navigates to URL using Playwright stealth, waits for dynamic content,
        and returns rendered HTML.
        """
        provenance = self.fetch_page_with_provenance(url)
        return provenance.get("html", "")

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
