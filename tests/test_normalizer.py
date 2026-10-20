import pytest
from src.normalizer import DataNormalizer

@pytest.fixture
def normalizer():
    return DataNormalizer(["mariano's", "roundy's", "simple truth", "private selection", "kroger"])

def test_approximate_weight_detection(normalizer):
    assert normalizer.is_approximate_weight("Approx. 1.5 lb") is True
    assert normalizer.is_approximate_weight("1.2 lb approximately") is True
    assert normalizer.is_approximate_weight("approx 24 oz") is True
    assert normalizer.is_approximate_weight("estimated 10 oz") is True
    
    # Exact weights should return False
    assert normalizer.is_approximate_weight("16 oz") is False
    assert normalizer.is_approximate_weight("1 Gallon") is False
    assert normalizer.is_approximate_weight("500 g") is False
    assert normalizer.is_approximate_weight("") is False

def test_clean_price(normalizer):
    assert normalizer.clean_price("$12.98") == "12.98"
    assert normalizer.clean_price("Now $1,249.99") == "1249.99"
    assert normalizer.clean_price("0.68") == "0.68"
    assert normalizer.clean_price("Invalid") == ""
    assert normalizer.clean_price("") == ""

def test_private_brand_identification(normalizer):
    assert normalizer.is_store_private_brand("Simple Truth Organic Whole Milk", "Simple Truth") == "yes"
    assert normalizer.is_store_private_brand("Roundy's Pure Granulated Sugar", "Roundy's") == "yes"
    assert normalizer.is_store_private_brand("Private Selection Angus Beef", "Private Selection") == "yes"
    assert normalizer.is_store_private_brand("Mariano's Italian Sausage", "Mariano's") == "yes"
    assert normalizer.is_store_private_brand("Coca-Cola 12 Pack", "Coca-Cola") == "no"
    assert normalizer.is_store_private_brand("Lay's Classic Potato Chips", "Frito-Lay") == "no"

def test_volume_deals_parsing(normalizer):
    vol_desc, vol_price, dig_desc, dig_price = normalizer.parse_deals(
        promo_badge="",
        deal_description="2 for $5",
        displayed_promo_price="$5.00"
    )
    assert vol_desc == "2 for $5"
    assert vol_price == "5.00"
    assert dig_desc == ""
    assert dig_price == ""

def test_digital_deals_parsing(normalizer):
    vol_desc, vol_price, dig_desc, dig_price = normalizer.parse_deals(
        promo_badge="Clip Coupon: Save $2",
        deal_description="",
        displayed_promo_price="$7.98"
    )
    assert vol_desc == ""
    assert vol_price == ""
    assert "Clip Coupon" in dig_desc
    assert dig_price == "7.98"

def test_cashback_not_treated_as_digital_deal(normalizer):
    vol_desc, vol_price, dig_desc, dig_price = normalizer.parse_deals(
        promo_badge="Kroger Cash: Earn $1.50",
        deal_description="",
        displayed_promo_price=""
    )
    assert vol_desc == ""
    assert vol_price == ""
    assert dig_desc == ""
    assert dig_price == ""

def test_multipack_label_not_treated_as_promotion(normalizer):
    # Pack labels must be preserved in title/weight, but NOT treated as promotions
    vol_desc, vol_price, dig_desc, dig_price = normalizer.parse_deals(
        promo_badge="12-Pack",
        deal_description="",
        displayed_promo_price=""
    )
    assert vol_desc == ""
    assert vol_price == ""
    assert dig_desc == ""
    assert dig_price == ""

    vol_desc, vol_price, dig_desc, dig_price = normalizer.parse_deals(
        promo_badge="Family Size",
        deal_description="",
        displayed_promo_price=""
    )
    assert vol_desc == ""
    assert vol_price == ""
    assert dig_desc == ""
    assert dig_price == ""
