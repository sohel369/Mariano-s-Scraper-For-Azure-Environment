import os
import sys
import json
import argparse
import re
from typing import List, Dict, Any

REQUIRED_FIELD_ORDER = [
    "zipcode",
    "store_name",
    "store_location",
    "store_logo",
    "store_brand",
    "category",
    "sub_category",
    "product_title",
    "weight",
    "regular_price",
    "sale_price",
    "volume_deals_description",
    "volume_deals_price",
    "digital_deals_description",
    "digital_deals_price",
    "image_url",
    "url",
    "upc",
    "gupc",
    "ppm",
    "unit_price",
    "crawl_date"
]

def validate_dataset(filepath: str) -> bool:
    print(f"\nAUDITING DATASET: {filepath}")
    print("="*60)

    if not os.path.exists(filepath):
        print(f"FAIL: File does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        try:
            records: List[Dict[str, Any]] = json.load(f)
        except Exception as e:
            print(f"FAIL: Invalid JSON format: {e}")
            return False

    total_records = len(records)
    print(f"Total Records Found: {total_records}")

    if total_records < 500:
        print(f"WARNING: Contest demo requires at least 500 records. (Found {total_records})")

    errors = []
    approx_weight_count = 0
    null_value_count = 0
    invalid_field_order_count = 0
    invalid_gupc_count = 0
    invalid_unit_price_count = 0
    invalid_store_brand_count = 0

    approx_regex = re.compile(r'\bapprox(imately)?\b', re.IGNORECASE)

    categories_found = set()

    for idx, r in enumerate(records):
        keys = list(r.keys())
        # 1. Field order check
        if keys != REQUIRED_FIELD_ORDER:
            invalid_field_order_count += 1
            if invalid_field_order_count <= 3:
                errors.append(f"Record #{idx} keys do not match required order.")

        # 2. Check for null values
        for k, v in r.items():
            if v is None:
                null_value_count += 1
                if null_value_count <= 3:
                    errors.append(f"Record #{idx} contains null in field '{k}'. (Must be empty string)")

        # 3. Check approx weight exclusion
        w = r.get("weight", "")
        if approx_regex.search(w):
            approx_weight_count += 1
            errors.append(f"Record #{idx} contains approximate weight: '{w}'")

        # 4. Check gupc and unit_price empty
        if r.get("gupc") != "":
            invalid_gupc_count += 1
        if r.get("unit_price") != "":
            invalid_unit_price_count += 1

        # 5. Check store_brand value
        if r.get("store_brand") not in ["yes", "no"]:
            invalid_store_brand_count += 1

        cat = r.get("category")
        if cat:
            categories_found.add(cat)

    print("\n--- COMPLIANCE CHECKS ---")
    print(f"1. Exact 22-Field Order Match: {'PASS' if invalid_field_order_count == 0 else f'FAIL ({invalid_field_order_count} errors)'}")
    print(f"2. Zero Nulls (All converted to ''): {'PASS' if null_value_count == 0 else f'FAIL ({null_value_count} nulls)'}")
    print(f"3. Exclude Approximate Weights: {'PASS' if approx_weight_count == 0 else f'FAIL ({approx_weight_count} found)'}")
    print(f"4. gupc is Empty String: {'PASS' if invalid_gupc_count == 0 else f'FAIL ({invalid_gupc_count} non-empty)'}")
    print(f"5. unit_price is Empty String: {'PASS' if invalid_unit_price_count == 0 else f'FAIL ({invalid_unit_price_count} non-empty)'}")
    print(f"6. store_brand is strictly 'yes'/'no': {'PASS' if invalid_store_brand_count == 0 else f'FAIL ({invalid_store_brand_count} invalid)'}")
    print(f"7. Unique Categories Covered: {len(categories_found)} ({', '.join(sorted(categories_found))})")
    print("="*60)

    is_clean = (
        invalid_field_order_count == 0 and
        null_value_count == 0 and
        approx_weight_count == 0 and
        invalid_gupc_count == 0 and
        invalid_unit_price_count == 0 and
        invalid_store_brand_count == 0
    )

    if is_clean:
        print("CONGRATULATIONS: Dataset passed 100% of contest compliance checks!")
    else:
        print("AUDIT FAILED: Please review the errors listed above.")

    return is_clean

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Mariano's Scraper Dataset")
    parser.add_argument("filepath", type=str, help="Path to JSON dataset to validate")
    args = parser.parse_args()
    validate_dataset(args.filepath)
