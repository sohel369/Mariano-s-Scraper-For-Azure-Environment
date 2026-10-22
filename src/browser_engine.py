
import os
import json
import time
import random
import logging
import hashlib

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from urllib.parse import quote

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Response,
    Error as PlaywrightError,
)

logger = logging.getLogger("MarianoScraper.BrowserEngine")


def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    """Calculate SHA-256 for the supplied bytes."""
    return hashlib.sha256(data).hexdigest()


def safe_response_headers(
    headers: Dict[str, str],
) -> Dict[str, str]:
    """Exclude common credential-bearing headers from evidence."""
    sensitive_headers = {
        "set-cookie",
        "authorization",
        "proxy-authorization",
        "www-authenticate",
    }

    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).lower() not in sensitive_headers
    }


def extract_store_ids(payload: Any) -> set:
    """
    Extract explicit store identity fields from a JSON payload.
    Generic 'id' fields are intentionally ignored.
    """
    identity_keys = {
        "locationid",
        "storeid",
        "fulfillmentstoreid",
        "store_id",
        "location_id",
        "fulfillment_store_id",
    }

    found = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in identity_keys:
                    if isinstance(child, (str, int)):
                        found.add(str(child))
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return found


class BrowserEngine:
    """
    Playwright browser engine for retailer page collection.

    Network failures are raised rather than silently replaced with
    cached, historical, or fabricated responses.
    """

    def __init__(
        self,
        settings: Dict[str, Any],
        proxy_config: Optional[Dict[str, Any]] = None,
    ):
        self.settings = settings.get("scraping", {})
        self.proxy_config = proxy_config or {}

        self.headless = bool(
            self.settings.get("headless", True)
        )

        self.page_timeout = int(
            self.settings.get("page_timeout_ms", 45000)
        )

        self.store_lookup_timeout = int(
            self.settings.get("store_lookup_timeout_ms", 15000)
        )

        self.min_delay = float(
            self.settings.get("request_delay_min_seconds", 2.0)
        )

        self.max_delay = float(
            self.settings.get("request_delay_max_seconds", 4.5)
        )

        if self.page_timeout <= 0:
            raise ValueError("page_timeout_ms must be positive")

        if self.store_lookup_timeout <= 0:
            raise ValueError(
                "store_lookup_timeout_ms must be positive"
            )

        if self.min_delay < 0 or self.max_delay < self.min_delay:
            raise ValueError("Invalid request delay configuration")

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def start(self) -> None:
        """Start Playwright and create a browser context."""
        if self._context is not None:
            return

        try:
            self._playwright = sync_playwright().start()

            launch_options: Dict[str, Any] = {
                "headless": self.headless,
            }

            if self.proxy_config.get("enabled"):
                server = (
                    self.proxy_config.get("http_proxy")
                    or self.proxy_config.get("https_proxy")
                )

                if not server:
                    raise ValueError(
                        "Proxy is enabled but no proxy server is configured"
                    )

                launch_options["proxy"] = {"server": server}

            self._browser = self._playwright.chromium.launch(
                **launch_options
            )

            self._context = self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=self.settings.get(
                    "user_agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36",
                ),
                locale="en-US",
                timezone_id="America/Chicago",
            )

            self._context.set_default_timeout(self.page_timeout)

            logger.info("Browser context started")

        except Exception:
            logger.exception("Failed to start browser engine")
            self.close()
            raise

    def set_store_location(
        self,
        location: Dict[str, Any],
    ) -> None:
        """
        Configure the requested store context.

        Cookies express a requested context; they do not independently
        prove that the retailer accepted that store selection.
        """
        if self._context is None:
            self.start()

        assert self._context is not None

        zipcode = str(location.get("zipcode", "60601"))
        division_id = str(location.get("division_id", "531"))
        store_number = str(location.get("store_number", "00503"))
        store_id = str(location.get("store_id", "53100503"))

        modality_value = json.dumps(
            {
                "intent": "PICKUP",
                "postalCode": zipcode,
                "divisionNumber": division_id,
                "storeNumber": store_number,
            },
            separators=(",", ":"),
        )

        cookies = [
            {
                "name": "postalCode",
                "value": zipcode,
                "domain": ".marianos.com",
                "path": "/",
            },
            {
                "name": "kroger.postalCode",
                "value": zipcode,
                "domain": ".marianos.com",
                "path": "/",
            },
            {
                "name": "kroger.storeId",
                "value": store_id,
                "domain": ".marianos.com",
                "path": "/",
            },
            {
                "name": "storeIntent",
                "value": "PICKUP",
                "domain": ".marianos.com",
                "path": "/",
            },
            {
                "name": "kroger.modality",
                "value": modality_value,
                "domain": ".marianos.com",
                "path": "/",
            },
        ]

        try:
            self._context.add_cookies(cookies)

            logger.info(
                "Requested store context configured: "
                "division=%s store_number=%s store_id=%s "
                "zipcode=%s modality=PICKUP",
                division_id,
                store_number,
                store_id,
                zipcode,
            )

        except Exception:
            logger.exception("Failed to configure store context")
            raise

    def fetch_live_store_lookup(
        self,
        store_id: str,
        location_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fetch a live store lookup response and verify store identity.

        Override MARIANOS_STORE_LOOKUP_URL_TEMPLATE if the retailer's
        documented/current endpoint differs from the default.
        """
        if self._context is None:
            self.start()

        assert self._context is not None

        store_id = str(store_id).strip()

        if not store_id:
            raise ValueError("store_id must not be empty")

        endpoint_template = os.environ.get(
            "MARIANOS_STORE_LOOKUP_URL_TEMPLATE",
            "https://www.marianos.com/api/v1/store/"
            "{store_id}?modality=PICKUP",
        )

        store_url = endpoint_template.format(
            store_id=quote(store_id, safe="")
        )

        logger.info("Requesting store lookup: %s", store_url)

        try:
            response = self._context.request.get(
                store_url,
                timeout=self.store_lookup_timeout,
                headers={"Accept": "application/json"},
            )

            response_bytes = response.body()
            response_headers = safe_response_headers(
                dict(response.headers)
            )

        except Exception as exc:
            logger.exception("Store lookup request failed")

            raise RuntimeError(
                "Store lookup failed before a usable HTTP response "
                "was received. Check connectivity, endpoint, timeout, "
                "and retailer access."
            ) from exc

        content_type = response_headers.get("content-type", "")

        response_metadata = {
            "status_code": response.status,
            "headers": response_headers,
            "content_type": content_type,
            "content_length_bytes": len(response_bytes),
            "body_sha256": sha256_bytes(response_bytes),
            "provenance_type": "fresh_live_http_response",
        }

        if not 200 <= response.status < 300:
            response_metadata["provenance_type"] = (
                "live_http_error_response"
            )

            raise RuntimeError(
                f"Live store lookup failed with HTTP {response.status}; "
                "no replay fallback is permitted."
            )

        # Use Playwright's JSON parser so invalid JSON is rejected.
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                "Live store lookup returned non-JSON content; "
                f"content-type={content_type!r}"
            ) from exc

        if not isinstance(payload, (dict, list)):
            raise RuntimeError(
                "Store lookup JSON must be an object or list"
            )

        observed_ids = extract_store_ids(payload)

        if not observed_ids:
            raise RuntimeError(
                "Store lookup JSON contains no recognized store ID; "
                "store identity cannot be verified."
            )

        if store_id not in observed_ids:
            raise RuntimeError(
                f"Store identity mismatch: requested {store_id}; "
                f"observed IDs: {sorted(observed_ids)}"
            )

        response_metadata["store_identity_verified"] = True
        response_metadata["observed_store_ids"] = sorted(observed_ids)

        return {
            "request_metadata": {
                "request_url": response.url,
                "timestamp": utc_now(),
                "method": "GET",
                "requested_store_id": store_id,
                "requested_fulfillment": "PICKUP",
            },
            "response_metadata": response_metadata,
            "raw_store_lookup_response": payload,
        }

    def fetch_page_with_provenance(
        self,
        url: str,
        run_id: str = "",
        category_key: str = "",
        store_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Capture a main-document HTTP response and rendered HTML.

        response_body_sha256 hashes HTTP response bytes.
        rendered_html_sha256 hashes page.content() output.
        These hashes refer to different artifacts.
        """
        if self._context is None:
            self.start()

        assert self._context is not None

        if not url.startswith(("https://", "http://")):
            raise ValueError("url must use HTTP or HTTPS")

        delay = random.uniform(self.min_delay, self.max_delay)

        if delay > 0:
            time.sleep(delay)

        page: Page = self._context.new_page()

        try:
            logger.info(
                "Navigating to %s; run_id=%s category=%s",
                url,
                run_id,
                category_key,
            )

            main_response: Optional[Response] = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.page_timeout,
            )

            if main_response is None:
                raise RuntimeError(
                    f"No main-document HTTP response received: {url}"
                )

            response_body = main_response.body()
            response_headers = safe_response_headers(
                dict(main_response.headers)
            )

            try:
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(500)
            except PlaywrightError:
                logger.warning(
                    "Post-navigation page interaction failed: %s",
                    url,
                )

            rendered_html = page.content()
            rendered_bytes = rendered_html.encode("utf-8")

            response_text = response_body.decode(
                "utf-8",
                errors="replace",
            )

            blocked_markers = (
                "access denied",
                "request blocked",
                "temporarily blocked",
            )

            marker_found = any(
                marker in response_text.lower()
                or marker in rendered_html.lower()
                for marker in blocked_markers
            )

            status = main_response.status
            is_blocked = status in (403, 429) or marker_found
            is_success = 200 <= status < 300 and not is_blocked

            return {
                "request_url": url,
                "final_url": page.url,
                "timestamp": utc_now(),
                "http_status": status,
                "response_headers": response_headers,
                "response_content_type": response_headers.get(
                    "content-type", ""
                ),
                "response_body_length_bytes": len(response_body),
                "response_body_sha256": sha256_bytes(response_body),
                "rendered_html_length_bytes": len(rendered_bytes),
                "rendered_html_sha256": sha256_bytes(rendered_bytes),
                "run_id": run_id,
                "category_key": category_key,
                "store_context": store_context or {},
                "response_received": True,
                "is_blocked": is_blocked,
                "is_success": is_success,
                "html": rendered_html,
            }

        except Exception:
            logger.exception(
                "Page collection failed: url=%s run_id=%s category=%s",
                url,
                run_id,
                category_key,
            )
            raise

        finally:
            try:
                page.close()
            except Exception:
                logger.warning(
                    "Failed to close page cleanly: %s",
                    url,
                    exc_info=True,
                )

    def fetch_page_content(self, url: str) -> str:
        """
        Backwards-compatible helper returning rendered HTML.
        Raises if the main page response is unsuccessful.
        """
        result = self.fetch_page_with_provenance(url)

        if not result["is_success"]:
            raise RuntimeError(
                "Page request was not successful: "
                f"HTTP {result['http_status']}; "
                f"blocked={result['is_blocked']}; URL={url}"
            )

        return result["html"]

    def close(self) -> None:
        """Close context, browser, and Playwright safely."""
        context = self._context
        browser = self._browser
        playwright = self._playwright

        self._context = None
        self._browser = None
        self._playwright = None

        if context is not None:
            try:
                context.close()
            except Exception:
                logger.warning(
                    "Error closing browser context",
                    exc_info=True,
                )

        if browser is not None:
            try:
                browser.close()
            except Exception:
                logger.warning(
                    "Error closing browser",
                    exc_info=True,
                )

        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                logger.warning(
                    "Error stopping Playwright",
                    exc_info=True,
                )
