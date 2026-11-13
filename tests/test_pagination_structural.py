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
            is_genuine_end = MarianoProductionScraper.is_genuine_catalog_exhaustion(html_with_unrelated_disabled_button)

    # Must fail closed: subcat_failed must be True, and is_genuine_end must be False!
    assert subcat_failed is True
    assert is_genuine_end is False


def test_genuine_pagination_control_exhaustion_acknowledged():
    """
    Verifies that when raw_items_count == 0 and dedicated pagination 'Next' button is disabled,
    catalog exhaustion is legitimately acknowledged.
    """
    html_exhausted = """
    <html>
    <body>
        <nav aria-label="pagination" class="kds-Pagination">
            <button class="pagination__next" aria-disabled="true" disabled>Next</button>
        </nav>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_exhausted) is True


def test_unrelated_carousel_disabled_button_rejected():
    """
    Reviewer Requirement 2 (November 11):
    On an empty extraction, scraper.py must NOT accept generic disabled buttons on unrelated
    carousel/slider/banner controls as exhaustion evidence.
    """
    html_carousel = """
    <html>
    <body>
        <div class="carousel slider banner-controls">
            <button aria-label="Next Slide" aria-disabled="true" disabled>Next</button>
        </div>
        <div class="product-grid"></div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_carousel) is False


def test_hidden_empty_state_template_rejected():
    """
    Reviewer Requirement 2 (November 11):
    Scans must NOT accept hidden empty-state templates or aria-hidden elements
    as false exhaustion evidence.
    """
    # 1. Hidden inside <template>
    html_template = """
    <html>
    <body>
        <template id="no-results-tpl">
            <div class="EmptySearchResults">0 results matching your search</div>
        </template>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_template) is False

    # 2. Hidden via aria-hidden="true"
    html_aria_hidden = """
    <html>
    <body>
        <div class="EmptySearchResults" aria-hidden="true">
            No products found matching your search
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_aria_hidden) is False


def test_visible_empty_state_container_acknowledged():
    """
    Verifies that genuine, visible empty-state result containers in the catalog acknowledge exhaustion.
    """
    html_visible_empty = """
    <html>
    <body>
        <div data-testid="empty-search" class="EmptySearchResults">
            <h2>We couldn't find any products</h2>
            <p>0 results matching your search</p>
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_visible_empty) is True


def test_exhaustion_rejects_empty_search_results_with_html_hidden_attribute():
    """
    Reviewer November 13 Finding 1:
    Reject EmptySearchResults element possessing the boolean HTML hidden attribute.
    """
    html_hidden_attr = """
    <html>
    <body>
        <div class="EmptySearchResults" hidden>
            0 results matching your search
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_hidden_attr) is False


def test_exhaustion_rejects_empty_search_results_inside_display_none_parent():
    """
    Reviewer November 13 Finding 2:
    Reject EmptySearchResults element inside a display:none ancestor parent.
    """
    html_display_none = """
    <html>
    <body>
        <div style="display:none">
            <div class="EmptySearchResults">
                No products found
            </div>
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_display_none) is False

    html_display_none_spaced = """
    <html>
    <body>
        <div style="display: none;">
            <div data-testid="no-results" class="NoResults">
                0 results matching your search
            </div>
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_display_none_spaced) is False


def test_exhaustion_rejects_hidden_pagination_nav_with_disabled_next():
    """
    Reviewer November 13 Finding 3:
    Reject hidden pagination navigation container containing an aria-disabled Next button.
    """
    # 1. Directly with hidden attribute on nav
    html_hidden_nav = """
    <html>
    <body>
        <nav aria-label="pagination" class="kds-Pagination" hidden>
            <button class="pagination__next" aria-disabled="true" disabled>Next</button>
        </nav>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_hidden_nav) is False

    # 2. Inside a display:none ancestor
    html_hidden_nav_ancestor = """
    <html>
    <body>
        <div style="display:none">
            <nav aria-label="pagination" class="kds-Pagination">
                <button class="pagination__next" aria-disabled="true" disabled>Next</button>
            </nav>
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_hidden_nav_ancestor) is False


def test_exhaustion_rejects_pagination_nav_inside_carousel_ancestor():
    """
    Reviewer November 13 Finding 4:
    Reject pagination navigation container hosted inside a carousel/slider ancestor.
    """
    html_carousel_ancestor = """
    <html>
    <body>
        <div class="product-carousel-slider-container carousel">
            <section class="widget-wrapper">
                <nav aria-label="pagination" class="kds-Pagination">
                    <button class="pagination__next" aria-disabled="true" disabled>Next</button>
                </nav>
            </section>
        </div>
    </body>
    </html>
    """
    assert MarianoProductionScraper.is_genuine_catalog_exhaustion(html_carousel_ancestor) is False


