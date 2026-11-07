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
