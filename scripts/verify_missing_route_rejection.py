#!/usr/bin/env python3
"""
scripts/verify_missing_route_rejection.py
Demonstrates and proves that the 100% publication gate strictly REJECTS and aborts
dataset commit if even a single required category or subcategory route is missing, omitted,
or encounters an unhandled failure during traversal.
"""

import os
import sys
import json
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.storage_manager import StorageManager

def run_proof():
    print("=" * 85)
    print("MARIANO'S SCRAPER: MISSING-ROUTE REJECTION PUBLICATION GATE PROOF")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 85)

    with tempfile.TemporaryDirectory(prefix="marianos_gate_proof_") as temp_dir:
        storage = StorageManager(base_dir=temp_dir, min_records_threshold=10)
        store_id = "53100503"
        staging_file = os.path.join(storage.staging_dir, "staging_proof.jsonl")

        # Define 28 expected subcategories from the 14 parent departments
        expected_28 = [
            "Fresh Produce::Fresh Fruits", "Fresh Produce::Fresh Vegetables",
            "Meat & Seafood::Poultry & Fresh Meat", "Meat & Seafood::Seafood & Shellfish",
            "Dairy & Eggs::Milk & Plant Alternatives", "Dairy & Eggs::Eggs Butter & Yogurt",
            "Bakery::Fresh Bread & Rolls", "Bakery::Pastries Cakes & Pies",
            "Deli::Sliced Deli Meats & Cheeses", "Deli::Prepared Dips & Ready Meals",
            "Pantry::Canned Goods Soups & Grains", "Pantry::Snacks Condiments & Sauces",
            "Beverages::Bottled Water & Soft Drinks", "Beverages::Coffee Tea & Fruit Juices",
            "Frozen Foods::Frozen Meals & Entrees", "Frozen Foods::Ice Cream & Frozen Desserts",
            "Natural & Organic::Organic Produce & Dairy", "Natural & Organic::Organic Pantry & Snacks",
            "Cleaning & Household::Laundry Care & Paper Goods", "Cleaning & Household::Surface Cleaners & Dish Care",
            "Personal Care::Body Wash & Hair Care", "Personal Care::Oral Care & Deodorants",
            "Health & Wellness::Vitamins & Nutrition", "Health & Wellness::OTC Medicine & First Aid",
            "Baby Care::Baby Food & Formula", "Baby Care::Diapers Wipes & Baby Bath",
            "Pet Care::Dog Food & Treats", "Pet Care::Cat Food & Litter"
        ]

        # Case 1: Incomplete run (27 of 28 completed, 1 omitted)
        omitted_route = expected_28[-1]  # "Pet Care::Cat Food & Litter"
        incomplete_27 = expected_28[:-1]

        # Write 560 valid staged records covering the 27 completed routes
        for i in range(560):
            cat_key = incomplete_27[i % len(incomplete_27)]
            dept, sub = cat_key.split("::")
            storage.write_staging_record(staging_file, {
                "upc": f"0111100{i:05d}",
                "category": dept,
                "sub_category": sub
            })

        storage.save_checkpoint(
            store_id=store_id,
            completed_subcategories=incomplete_27,
            scraped_ids=[f"0111100{i:05d}" for i in range(560)]
        )

        print(f"\n[TEST 1] EVALUATING INCOMPLETE TRAVERSAL (27/28 Routes Completed):")
        print(f"  • Expected Total Routes: 28")
        print(f"  • Completed Routes:      27")
        print(f"  • Intentionally Omitted: {omitted_route}")
        print(f"  • Total Staged Records:  560")

        # Execute gate
        commit_result = storage.commit_dataset_atomic(
            store_id=store_id,
            staging_filepath=staging_file,
            total_categories_expected=28,
            categories_processed=27,
            expected_category_keys=expected_28,
            actual_completed_keys=incomplete_27
        )

        target_output = os.path.join(storage.output_dir, f"marianos_scraped_data_store_{store_id}_latest.json")
        file_prevented = not os.path.exists(target_output)

        print(f"\n[GATE OUTCOME]:")
        print(f"  • commit_dataset_atomic() returned: {commit_result} (Expected: False)")
        print(f"  • Output file write prevented:      {file_prevented} (Expected: True)")
        assert commit_result is False
        assert file_prevented is True
        print(f"  -> PROOF: Gate successfully ABORTED publication upon missing route: {omitted_route}")

        # Case 2: Full 28 of 28 completed
        print(f"\n[TEST 2] EVALUATING FULL 100% TRAVERSAL (28/28 Routes Completed):")
        # Add records for the missing route
        for i in range(20):
            storage.write_staging_record(staging_file, {
                "upc": f"0222200{i:05d}",
                "category": "Pet Care",
                "sub_category": "Cat Food & Litter"
            })
        storage.save_checkpoint(
            store_id=store_id,
            completed_subcategories=expected_28,
            scraped_ids=[f"0111100{i:05d}" for i in range(560)] + [f"0222200{i:05d}" for i in range(20)]
        )

        full_commit_result = storage.commit_dataset_atomic(
            store_id=store_id,
            staging_filepath=staging_file,
            total_categories_expected=28,
            categories_processed=28,
            expected_category_keys=expected_28,
            actual_completed_keys=expected_28
        )
        file_created = os.path.exists(target_output)
        print(f"  • commit_dataset_atomic() returned: {full_commit_result} (Expected: True)")
        print(f"  • Output file written atomically:   {file_created} (Expected: True)")
        assert full_commit_result is True
        assert file_created is True
        print(f"  -> PROOF: Gate successfully COMMITTED dataset only when 100% of 28 routes were satisfied.")

        # Save audit artifact
        audit_log = {
            "proof_name": "MISSING_ROUTE_REJECTION_GATE_VERIFICATION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "100% PASS - GATE STRICTLY ENFORCED",
            "test_1_incomplete_route": {
                "expected_routes_count": 28,
                "completed_routes_count": 27,
                "omitted_route": omitted_route,
                "gate_rejected_commit": True,
                "output_file_prevented": True
            },
            "test_2_full_route": {
                "expected_routes_count": 28,
                "completed_routes_count": 28,
                "gate_approved_commit": True,
                "output_file_created": True
            }
        }

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        log_path = os.path.join(base_dir, "logs", "missing_route_rejection_audit_proof.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(audit_log, f, indent=2)

        print("\n" + "=" * 85)
        print(f"Machine-readable proof saved to: {log_path}")
        print("MISSING-ROUTE REJECTION GATE: VERIFIED & PROVEN (100% PASS)")
        print("=" * 85)

if __name__ == "__main__":
    run_proof()
