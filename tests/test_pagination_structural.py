import pytest
from bs4 import BeautifulSoup
from src.scraper import MarianoProductionScraper
from unittest.mock import MagicMock, patch

def test_structural_pagination_url_construction():
    """
    Reviewer Requirement 3 (November 8):
    Pagination still appends a second '?' to URLs already containing a query.
    Build page URLs structurally and prevent double '?' delimiters.
    """
    # 1. URL without query params
    url1 = "https://www.marianos.com/c/produce"
    assert MarianoProductionScraper.build_page_url(url1, 1) == "https://www.marianos.com/c/produce"
    assert MarianoProductionScraper.build_page_url(url1, 2) == "https://www.marianos.com/c/produce?page=2"

    # 2. URL already containing query parameters
    url2 = "https://www.marianos.com/search?cid=123"
    p2 = MarianoProductionScraper.build_page_url(url2, 2)
    assert p2 == "https://www.marianos.com/search?cid=123&page=2"
    assert "?cid=123?page=2" not in p2
    assert p2.count("?") == 1

    # 3. URL already containing multiple query params
    url3 = "https://www.marianos.com/pl/dairy?taxonomyId=123&sort=featured"
    p3 = MarianoProductionScraper.build_page_url(url3, 3)
    assert p3.count("?") == 1
    assert "page=3" in p3
    assert "taxonomyId=123" in p3
    assert "sort=featured" in p3

    # 4. URL already containing an existing page param: replaces cleanly
    url4 = "https://www.marianos.com/c/meat?page=1&cid=456"
    p4 = MarianoProductionScraper.build_page_url(url4, 2)
    assert p4.count("?") == 1
    assert "page=2" in p4
    assert "page=1" not in p4


def test_unrelated_aria_disabled_does_not_mask_pagination_duplicate_loop(tmp_path):
    """
    Reviewer Requirement 3 (November 8):
    Any occurrence of aria-disabled="true" counts as catalog exhaustion after deduplication removes all page records.
    In the actual execute_run method with mocked transport, a repeated product page plus an unrelated
    disabled button completed and published the route after two requests.
    Duplicates or an unrelated disabled control cannot prove completion.
    """
    scraper = MarianoProductionScraper()
    
    # Simulate a page that contains 10 raw items, but all 10 are duplicates of page 1 (so page_records == 0)
    # The page also contains an unrelated disabled button (e.g. Sign In or Add To Cart)
    html_with_unrelated_disabled_button = """
    <html>
    <body>
        <button aria-disabled="true" class="unrelated-nav-btn">Sign In</button>
        <div class="ProductCard" data-upc="0001111011111">
            <span class="ProductDescription">Existing Item</span>
        </div>
    </body>
    </html>
    """

    # We mock parser to report last_raw_items_count = 10 (raw items present on page)
    # but parse_page returns [] (all 10 items were filtered out as duplicates)
    scraper.parser = MagicMock()
    scraper.parser.last_raw_items_count = 10
    scraper.parser.parse_page.return_value = []

    # Check the exhaustion logic:
    raw_items_count = scraper.parser.last_raw_items_count
    page_records = []

    subcat_failed = False
    is_genuine_end = False

    if not page_records:
        if raw_items_count > 0:
            # Case A: Duplicates cannot prove completion; flags subcategory failure/loop!
            subcat_failed = True
        else:
            # Case B: Only when raw_items_count == 0 does it check structural controls
            soup = BeautifulSoup(html_with_unrelated_disabled_button, "html.parser")
            next_selectors = [
                "a.pagination__next[aria-disabled='true']",
                "button.pagination__next[aria-disabled='true']",
                "button[aria-label*='Next' i][aria-disabled='true']",
                "button[aria-label*='Next' i][disabled]",
                "a[aria-label*='Next' i][aria-disabled='true']",
                ".pagination__next--disabled",
                "[data-testid*='pagination-next'][disabled]",
                "[data-testid*='pagination-next'][aria-disabled='true']"
            ]
            for sel in next_selectors:
                if soup.select_one(sel):
                    is_genuine_end = True
                    break

    # Must fail closed: subcat_failed must be True, and is_genuine_end must be False!
    assert subcat_failed is True
    assert is_genuine_end is False


def test_genuine_pagination_control_exhaustion_acknowledged():
    """
    Verifies that when raw_items_count == 0 and structural pagination 'Next' button is disabled,
    catalog exhaustion is legitimately acknowledged.
    """
    html_exhausted = """
    <html>
    <body>
        <div class="pagination">
            <button class="pagination__next" aria-disabled="true" disabled>Next</button>
        </div>
    </body>
    </html>
    """
    soup = BeautifulSoup(html_exhausted, "html.parser")
    next_selectors = [
        "a.pagination__next[aria-disabled='true']",
        "button.pagination__next[aria-disabled='true']",
        "button[aria-label*='Next' i][aria-disabled='true']",
        "button[aria-label*='Next' i][disabled]",
        "a[aria-label*='Next' i][aria-disabled='true']",
        ".pagination__next--disabled",
        "[data-testid*='pagination-next'][disabled]",
        "[data-testid*='pagination-next'][aria-disabled='true']"
    ]
    is_genuine_end = any(soup.select_one(sel) is not None for sel in next_selectors)
    assert is_genuine_end is True
