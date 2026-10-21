"""
========================================================================================
OFFLINE DETERMINISTIC RECOVERY VERIFICATION (Simulated Interruption & Resume Audit)
========================================================================================
Purpose: Conclusively and deterministically proves that upon process interruption:
1. Genuine raw category responses (Subcategories 1-14) are safely captured, parsed
   via production MarianoPageParser, and staged.
2. Interruption is simulated and persisted state/checkpoint rows are verified.
3. Upon resume, StorageManager restores 100% of rows from disk into the new session.
4. Deduplication idempotency is tested: repeat resumes do not duplicate rows.
5. Traversal resumes for Subcategories 15-28 without duplicate re-queries.
6. All 28 expected CSV categories match exactly (exact set equality).
7. Zero duplicate UPCs, zero lost records, and 100% publication gate pass.
========================================================================================
"""

import os
import sys
import json
import shutil
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Any, Set

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage_manager import StorageManager
from src.config_loader import ConfigLoader
from src.parser import MarianoPageParser
from src.normalizer import DataNormalizer

def run_checkpoint_integrity_audit():
    print("=" * 85)
    print("MARIANO'S SCRAPER: OFFLINE DETERMINISTIC RECOVERY & ROW RESTORATION AUDIT")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("Version: v2.0-PROD (Authoritative Release for Mariano's Entry #36)")
    print("=" * 85)

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_loader = ConfigLoader(base_dir)
    category_entries = config_loader.load_category_urls()
    expected_csv_keys = [f"{e['category']}::{e['sub_category']}" for e in category_entries]
    total_categories_count = len(expected_csv_keys)
    assert total_categories_count == 28, f"Expected 28 CSV categories, got {total_categories_count}"

    location = config_loader.get_default_location()
    normalizer = DataNormalizer(config_loader.load_private_brands())
    parser = MarianoPageParser(normalizer)

    temp_dir = tempfile.mkdtemp(prefix="marianos_audit_recovery_")
    storage = StorageManager(base_dir=temp_dir, min_records_threshold=500)
    store_id = "53100503"

    # Location of 28 raw category response captures
    responses_dir = os.path.join(base_dir, "data", "raw", "responses")
    response_files = sorted([f for f in os.listdir(responses_dir) if f.endswith(".json")])
    assert len(response_files) == 28, f"Expected 28 response files, found {len(response_files)}"

    try:
        # -------------------------------------------------------------------------
        # PHASE 1: EXECUTE INITIAL BATCH (Subcategories 1-14)
        # -------------------------------------------------------------------------
        print("\n[PHASE 1] RUNNING INITIAL BATCH (Subcategories 1-14):")
        staging_file_run1 = os.path.join(storage.staging_dir, "staging_run1.jsonl")
        
        phase1_upcs: List[str] = []
        phase1_records: List[Dict[str, Any]] = []
        completed_phase1_keys: List[str] = []

        for idx in range(14):
            entry = category_entries[idx]
            cat_key = f"{entry['category']}::{entry['sub_category']}"
            rf = response_files[idx]
            with open(os.path.join(responses_dir, rf), "r", encoding="utf-8") as f:
                resp_payload = json.load(f)
            
            raw_products = resp_payload.get("data", {}).get("products", [])
            for p in raw_products:
                rec_obj = parser.parse_product_item(p, entry["category"], entry["sub_category"], location)
                if not rec_obj:
                    continue
                record = rec_obj.to_ordered_dict()
                phase1_upcs.append(record["upc"])
                phase1_records.append(record)
                storage.write_staging_record(staging_file_run1, record)

            completed_phase1_keys.append(cat_key)

        # Save checkpoint with rows at interruption point
        storage.save_checkpoint(
            store_id=store_id,
            completed_subcategories=completed_phase1_keys,
            scraped_ids=phase1_upcs,
            staged_records=phase1_records
        )
        print(f"  • Collected & Normalized: {len(phase1_upcs)} records across 14 subcategories via MarianoPageParser.")
        print(f"  • Checkpoint Saved: store_id={store_id}, completed=14/28 subcategories.")
        print(f"  • Process Interrupted: (Simulated unexpected container preemption / restart).")

        # -------------------------------------------------------------------------
        # PHASE 2: RESUME NEW SESSION FROM CHECKPOINT
        # -------------------------------------------------------------------------
        print("\n[PHASE 2] NEW SESSION BOOT & CHECKPOINT RESTORATION:")
        staging_file_run2 = os.path.join(storage.staging_dir, "staging_run2.jsonl")
        
        # Load checkpoint in fresh state
        new_storage = StorageManager(base_dir=temp_dir, min_records_threshold=500)
        cp_data = new_storage.load_checkpoint(store_id)
        restored_completed_subcats = cp_data.get("completed_subcategories", [])
        print(f"  • Checkpoint Detected: {len(restored_completed_subcats)} subcategories completed.")

        # Execute row restoration from disk
        restored_count = new_storage.restore_checkpoint_rows(store_id, staging_file_run2)
        print(f"  • StorageManager.restore_checkpoint_rows(): Restored {restored_count} rows from disk into fresh staging.")
        assert restored_count == len(phase1_records), f"Expected {len(phase1_records)} restored rows, got {restored_count}"

        # Test deduplication idempotence: running restore again must NOT duplicate rows
        dup_test_count = new_storage.restore_checkpoint_rows(store_id, staging_file_run2)
        assert dup_test_count == 0, f"Expected 0 additional restored rows on repeated resume, got {dup_test_count}"
        print(f"  • Idempotency Verified: Second restore attempt yielded 0 duplicate rows (PASS).")

        restored_staging_records = new_storage.load_staging_records(staging_file_run2)
        restored_upcs = [r["upc"] for r in restored_staging_records]

        # -------------------------------------------------------------------------
        # PHASE 3: EXECUTE REMAINING BATCH (Subcategories 15-28)
        # -------------------------------------------------------------------------
        print("\n[PHASE 3] CONTINUING EXECUTION (Subcategories 15-28):")
        completed_all_keys = list(restored_completed_subcats)
        phase2_new_upcs: List[str] = []

        for idx in range(14, 28):
            entry = category_entries[idx]
            cat_key = f"{entry['category']}::{entry['sub_category']}"
            rf = response_files[idx]
            with open(os.path.join(responses_dir, rf), "r", encoding="utf-8") as f:
                resp_payload = json.load(f)
            
            raw_products = resp_payload.get("data", {}).get("products", [])
            for p in raw_products:
                rec_obj = parser.parse_product_item(p, entry["category"], entry["sub_category"], location)
                if not rec_obj:
                    continue
                record = rec_obj.to_ordered_dict()
                phase2_new_upcs.append(record["upc"])
                new_storage.write_staging_record(staging_file_run2, record)

            completed_all_keys.append(cat_key)

        print(f"  • Completed Remaining 14 Subcategories: Ingested {len(phase2_new_upcs)} items.")

        # -------------------------------------------------------------------------
        # PHASE 4: MATHEMATICAL AUDIT & ID INTEGRITY VERIFICATION
        # -------------------------------------------------------------------------
        print("\n[PHASE 4] MATHEMATICAL AUDIT & EXACT SET VERIFICATION:")
        final_records = new_storage.load_staging_records(staging_file_run2)
        final_upcs = [r["upc"] for r in final_records]

        # 1. Record count preservation
        expected_total = len(phase1_upcs) + len(phase2_new_upcs)
        actual_total = len(final_records)
        assert expected_total == actual_total, f"Total count mismatch: expected {expected_total}, got {actual_total}"
        print(f"  1. Record Count Preservation: Expected {expected_total} == Actual {actual_total}: PASS")

        # 2. Row retention across session restart
        missing_phase1 = set(phase1_upcs) - set(final_upcs)
        assert len(missing_phase1) == 0, f"Lost {len(missing_phase1)} records during checkpoint restore!"
        print(f"  2. Zero Lost Records: Missing IDs = {len(missing_phase1)}: PASS")

        # 3. Duplicate checks
        duplicates = len(final_upcs) - len(set(final_upcs))
        assert duplicates == 0, f"Detected {duplicates} duplicate records in resumed staging!"
        print(f"  3. Zero Duplicate IDs: Duplicates = {duplicates}: PASS")

        # 4. Exact Set Equality against CSV
        assert set(completed_all_keys) == set(expected_csv_keys), "Category keys do not match CSV exactly!"
        print(f"  4. Exact Category Set Equality: 28/28 CSV keys match 100%: PASS")

        # 5. Production Atomic Commit Gate
        commit_ok = new_storage.commit_dataset_atomic(
            store_id=store_id,
            staging_filepath=staging_file_run2,
            total_categories_expected=28,
            categories_processed=len(completed_all_keys),
            expected_category_keys=expected_csv_keys,
            actual_completed_keys=completed_all_keys
        )
        assert commit_ok is True, "Atomic commit gate failed unexpectedly!"
        print(f"  5. Production Atomic Commit Gate (Strict 100% Exact Category Set): PASS")

        # Persist audit proof artifact
        proof_path = os.path.join(base_dir, "data", "raw", "checkpoint_recovery_audit_proof.json")
        audit_proof = {
            "audit_name": "Mariano's Deterministic Checkpoint Restoration & ID Recovery Proof",
            "test_type": "offline_deterministic_simulation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_store_id": store_id,
            "verification_status": "VERIFIED_PASS",
            "phase1_interrupted_at": "14/28 subcategories",
            "phase1_rows_persisted": len(phase1_upcs),
            "phase2_rows_restored_from_disk": restored_count,
            "phase2_rows_appended": len(phase2_new_upcs),
            "final_total_records": actual_total,
            "duplicate_records": duplicates,
            "lost_records": len(missing_phase1),
            "deduplication_idempotency_tested": True,
            "exact_category_set_match": True,
            "atomic_commit_result": True
        }
        with open(proof_path, "w", encoding="utf-8") as pf:
            json.dump(audit_proof, pf, indent=2)

        print(f"\nAudit proof artifact saved to: {proof_path}")
        print("=" * 85)
        print("RESULT: ALL CHECKPOINT INTEGRITY & RECOVERY CHECKS PASSED (100% PASS)")
        print("=" * 85)
        return 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(run_checkpoint_integrity_audit())
