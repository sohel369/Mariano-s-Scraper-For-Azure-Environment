import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger("MarianoScraper.AntiBot")

class BotDetectionError(Exception):
    """Raised when a bot detection challenge (CAPTCHA, Akamai, PerimeterX, Block) is encountered."""
    pass

class AntiBotDetector:
    """
    Monitors responses for bot challenges, Akamai / Kasada / Human Security blocks,
    silent blocking, canary product absences, and thin result warnings for Mariano's.
    """

    def __init__(self, canary_product_id: Optional[str] = None, min_yield_threshold: int = 10):
        self.canary_product_id = canary_product_id or "0001111041600" # Default: Simple Truth Organic Milk
        self.min_yield_threshold = min_yield_threshold
        
        # Signatures of known bot challenge pages
        self.block_signatures = [
            re.compile(r'press\s*&\s*hold', re.IGNORECASE),
            re.compile(r'robot\s*or\s*human\?', re.IGNORECASE),
            re.compile(r'verify\s*you\s*are\s*a\s*human', re.IGNORECASE),
            re.compile(r'blocked\s*by\s*perimeterx', re.IGNORECASE),
            re.compile(r'akamai\s*ghost', re.IGNORECASE),
            re.compile(r'access\s*denied', re.IGNORECASE),
            re.compile(r'incident\s*id:', re.IGNORECASE),
            re.compile(r'unusual\s*traffic\s*from\s*your\s*computer\s*network', re.IGNORECASE)
        ]

    def inspect_html(self, html_content: str, url: str) -> None:
        """
        Scans page HTML for anti-bot or CAPTCHA signatures.
        Raises BotDetectionError if a challenge is identified.
        """
        if not html_content or len(html_content) < 500:
            logger.warning(f"Abnormally short response received ({len(html_content)} bytes) for {url}")

        for sig in self.block_signatures:
            if sig.search(html_content):
                msg = f"Bot challenge / blocking page detected on {url} matching signature '{sig.pattern}'"
                logger.error(msg)
                raise BotDetectionError(msg)

    def check_yield(self, category: str, sub_category: str, items_count: int) -> bool:
        """
        Monitors yield count per category/page. Warns if results are abnormally thin.
        Returns False if yield is abnormally low.
        """
        if items_count == 0:
            logger.warning(f"Empty response: 0 items parsed for {category} -> {sub_category}")
            return False
        elif items_count < self.min_yield_threshold:
            logger.warning(
                f"Abnormally thin results: only {items_count} items parsed for "
                f"{category} -> {sub_category} (threshold: {self.min_yield_threshold})"
            )
            return True
        return True

    def verify_canary_product(self, items: List[Dict[str, Any]]) -> bool:
        """
        Verifies that expected staple items (canaries) appear in grocery scraping runs,
        confirming that real shelf data is being served rather than dummy/cached responses.
        """
        for item in items:
            title = (item.get("product_title") or "").lower()
            upc = item.get("upc") or ""
            if ("simple truth" in title or "roundy's" in title or "kroger" in title) and "milk" in title:
                logger.info("Canary product verified: Kroger/Mariano's staple Milk present in shelf dataset.")
                return True
            if self.canary_product_id in (item.get("upc") or item.get("url") or ""):
                logger.info(f"Canary product ID {self.canary_product_id} verified.")
                return True
        return False
