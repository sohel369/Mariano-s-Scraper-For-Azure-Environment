import pytest
from src.parser import MarianoPageParser
from src.normalizer import DataNormalizer

@pytest.fixture
def parser():
    normalizer = DataNormalizer()
    return MarianoPageParser(normalizer=normalizer)

@pytest.fixture
def location_info():
    return {
        "store_id": "53100503",
        "store_number": "00503",
        "division_id": "531",
        "zipcode": "60601",
        "store_name": "Mariano's New Eastside",
        "store_location": "333 E Benton Pl, Chicago, IL 60601",
        "store_logo": "https://www.marianos.com/content/v2/binary/image/marianos-logo.svg",
        "fulfillment_intent": "PICKUP"
    }

def test_item_fulfillment_not_pickup_retains_identity_with_blank_price(parser, location_info):
    """
    Reviewer Finding 1:
    Under a pickup page, item fulfillment NOT_PICKUP must NOT export price 3.25.
    Must retain eligible identity with blank unverified monetary values.
    """
    raw_item = {
        "name": "Kroger Pure Granulated Sugar",
        "upc": "0001111000123",
        "modality": "NOT_PICKUP",
        "priceInfo": {
            "currentPrice": {"price": 3.25, "priceString": "$3.25"},
            "wasPrice": {"price": 3.99, "priceString": "$3.99"}
        },
        "packageInfo": {"weight": "4 lb"},
        "canonicalUrl": "/p/kroger-sugar/0001111000123"
    }

    record = parser.parse_product_item(raw_item, "Pantry", "Baking", location_info)
    assert record is not None
    # Product identity is preserved
    assert record.product_title == "Kroger Pure Granulated Sugar"
    assert record.upc == "0001111000123"
    assert record.url == "https://www.marianos.com/p/kroger-sugar/0001111000123"
    assert record.weight == "4 lb"

    # Monetary values MUST be blank
    assert record.regular_price == ""
    assert record.sale_price == ""
    assert record.ppm == ""
    assert record.volume_deals_price == ""
    assert record.digital_deals_price == ""

def test_numeric_pickup_flag_minus_one_retains_identity_with_blank_price(parser, location_info):
    """
    Reviewer Finding 1:
    Numeric pickup flag -1 must NOT export price 3.25.
    Must retain eligible identity with blank unverified monetary values.
    """
    raw_item = {
        "name": "Heritage Farm Boneless Chicken Breast",
        "upc": "0001111041600",
        "pickup": -1,
        "priceInfo": {
            "currentPrice": {"price": 3.25, "priceString": "$3.25"}
        },
        "packageInfo": {"weight": "3 lb"},
        "canonicalUrl": "/p/heritage-farm-chicken/0001111041600"
    }

    record = parser.parse_product_item(raw_item, "Meat & Seafood", "Chicken", location_info)
    assert record is not None
    assert record.product_title == "Heritage Farm Boneless Chicken Breast"
    assert record.upc == "0001111041600"
    assert record.regular_price == ""
    assert record.sale_price == ""
    assert record.ppm == ""

def test_missing_item_offer_context_retains_identity_with_blank_price(parser, location_info):
    """
    Reviewer Finding 1:
    Missing item offer context must NOT export price.
    Must retain eligible identity with blank unverified monetary values.
    """
    raw_item = {
        "name": "Simple Truth Organic Whole Milk",
        "upc": "0001111088888",
        # No modality or pickup indicators provided on the item
        "priceInfo": {
            "currentPrice": {"price": 4.50, "priceString": "$4.50"}
        },
        "packageInfo": {"weight": "1 gal"},
        "canonicalUrl": "/p/simple-truth-milk/0001111088888"
    }

    record = parser.parse_product_item(raw_item, "Dairy & Eggs", "Milk", location_info)
    assert record is not None
    assert record.product_title == "Simple Truth Organic Whole Milk"
    assert record.upc == "0001111088888"
    assert record.regular_price == ""
    assert record.sale_price == ""

def test_positive_explicit_pickup_context_exports_price(parser, location_info):
    """
    Positive explicit pickup context (modality='PICKUP') exports validated price.
    """
    raw_item = {
        "name": "Mariano's Sliced Sourdough Bread",
        "upc": "0001111055555",
        "modality": "PICKUP",
        "priceInfo": {
            "currentPrice": {"price": 3.25, "priceString": "$3.25"},
            "wasPrice": {"price": 4.00, "priceString": "$4.00"}
        },
        "packageInfo": {"weight": "24 oz"},
        "canonicalUrl": "/p/sourdough-bread/0001111055555"
    }

    record = parser.parse_product_item(raw_item, "Bakery", "Bread", location_info)
    assert record is not None
    assert record.product_title == "Mariano's Sliced Sourdough Bread"
    assert record.regular_price == "4.00"
    assert record.sale_price == "3.25"


def test_foreign_store_id_pickup_item_retains_identity_with_blank_price(parser):
    """
    Reviewer Requirement 1 (November 8):
    With Vernon Hills configured (53100502), an item explicitly marked locationId=53100503,
    modality=PICKUP and $3.25 must NOT export as a $3.25 Vernon Hills record.
    Accepts only the selected store's verified aliases, linkage between priced offer and store/PICKUP context.
    Retains eligible product identity with blank monetary fields.
    """
    vernon_hills_info = {
        "store_id": "53100502",
        "store_number": "00502",
        "division_id": "531",
        "zipcode": "60061",
        "store_name": "Mariano's Vernon Hills",
        "store_location": "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
        "store_logo": "https://www.marianos.com/content/v2/binary/image/marianos-logo.svg",
        "fulfillment_intent": "PICKUP"
    }

    raw_item = {
        "name": "Kroger Extra Large Eggs",
        "upc": "0001111089999",
        "locationId": "53100503",  # Explicit New Eastside location ID on foreign item
        "modality": "PICKUP",
        "priceInfo": {
            "currentPrice": {"price": 3.25, "priceString": "$3.25"},
            "wasPrice": {"price": 3.99, "priceString": "$3.99"}
        },
        "packageInfo": {"weight": "12 ct"},
        "canonicalUrl": "/p/kroger-eggs/0001111089999"
    }

    record = parser.parse_product_item(raw_item, "Dairy & Eggs", "Eggs", vernon_hills_info)
    assert record is not None
    assert record.product_title == "Kroger Extra Large Eggs"
    assert record.upc == "0001111089999"
    assert record.zipcode == "60061"
    assert record.store_name == "Mariano's Vernon Hills"
    # Strict store linkage: $3.25 price from store 53100503 must NOT be exported
    assert record.regular_price == ""
    assert record.sale_price == ""
    assert record.ppm == ""


def test_matching_store_id_pickup_item_exports_price(parser):
    """
    Verifies that when item's locationId matches configured store, price is accepted.
    """
    vernon_hills_info = {
        "store_id": "53100502",
        "store_number": "00502",
        "division_id": "531",
        "zipcode": "60061",
        "store_name": "Mariano's Vernon Hills",
        "store_location": "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
        "store_logo": "https://www.marianos.com/content/v2/binary/image/marianos-logo.svg",
        "fulfillment_intent": "PICKUP"
    }

    raw_item = {
        "name": "Kroger Grade A Large Eggs",
        "upc": "0001111089998",
        "locationId": "53100502",  # Matching Vernon Hills location ID
        "modality": "PICKUP",
        "priceInfo": {
            "currentPrice": {"price": 3.25, "priceString": "$3.25"},
            "wasPrice": {"price": 3.99, "priceString": "$3.99"}
        },
        "packageInfo": {"weight": "12 ct"},
        "canonicalUrl": "/p/kroger-eggs-large/0001111089998"
    }

    record = parser.parse_product_item(raw_item, "Dairy & Eggs", "Eggs", vernon_hills_info)
    assert record is not None
    assert record.product_title == "Kroger Grade A Large Eggs"
    assert record.sale_price == "3.25"
    assert record.regular_price == "3.99"


def test_dom_fallback_missing_price_card_retains_unpriced_identity(parser):
    """
    Reviewer Requirement 2 (November 8):
    The DOM fallback requires both title_elem and price_elem. A product card with a valid title,
    UPC and URL but no price produced zero records. Retain eligible unpriced identities in this path as well,
    with blank monetary fields, and add a missing-price-card regression.
    """
    vernon_hills_info = {
        "store_id": "53100502",
        "store_number": "00502",
        "division_id": "531",
        "zipcode": "60061",
        "store_name": "Mariano's Vernon Hills",
        "store_location": "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
        "store_logo": "https://www.marianos.com/content/v2/binary/image/marianos-logo.svg",
        "fulfillment_intent": "PICKUP"
    }

    # HTML without any price element
    html_content = """
    <html>
    <body>
        <div class="ProductCard" data-upc="0001111044444">
            <a class="ProductDescription" href="/p/organic-honeycrisp-apples/0001111044444">
                Organic Honeycrisp Apples
            </a>
            <!-- No price element present in this card -->
            <span class="ProductCard-size">2 lb pouch</span>
        </div>
    </body>
    </html>
    """

    records = parser.parse_page(html_content, "Produce", "Apples", vernon_hills_info)
    assert len(records) == 1
    rec = records[0]
    assert rec.product_title == "Organic Honeycrisp Apples"
    assert rec.upc == "0001111044444"
    assert "0001111044444" in rec.url
    assert rec.regular_price == ""
    assert rec.sale_price == ""
    assert rec.ppm == ""

