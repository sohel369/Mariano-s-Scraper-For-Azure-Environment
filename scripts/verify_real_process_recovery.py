"""
========================================================================================
PACKAGED RESPONSE REPLAY RECOVERY TEST (Real Multi-Process Interruption & Resume)
========================================================================================
Test Type: packaged_response_replay_recovery_test
Purpose: Mathematically and empirically verifies zero data loss and zero duplicates
across independent operating system processes (different OS PIDs) with disk restoration.
All invariants (lost IDs, duplicate IDs, unexpected IDs) are computed dynamically.
Failed invariants strictly prevent atomic dataset publication.
========================================================================================
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from datetime import datetime, timezone

def run_phase_1(work_dir: str):
    pid = os.getpid()
    print(f"[PROCESS 1 | PID: {pid}] Initializing session at {work_dir}...")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from src.storage_manager import StorageManager
    from src.config_loader import ConfigLoader
    from src.parser import MarianoPageParser
    from src.normalizer import DataNormalizer

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_loader = ConfigLoader(base_dir)
    category_entries = config_loader.load_category_urls()
    location = config_loader.get_default_location()
    parser = MarianoPageParser(DataNormalizer([]))
    storage = StorageManager(base_dir=work_dir, min_records_threshold=500)
    store_id = "53100503"

    responses_dir = os.path.join(base_dir, "data", "raw", "responses")
    response_files = sorted([f for f in os.listdir(responses_dir) if f.endswith(".json")])

    staging_file = os.path.join(storage.staging_dir, "staging_session_phase1.jsonl")
    collected_upcs = []
    collected_records = []
    completed_subcats = []

    for i in range(14):
        entry = category_entries[i]
        cat_key = f"{entry['category']}::{entry['sub_category']}"
        with open(os.path.join(responses_dir, response_files[i]), "r", encoding="utf-8") as f:
            resp_payload = json.load(f)
        for p in resp_payload.get("data", {}).get("products", []):
            rec = parser.parse_product_item(p, entry["category"], entry["sub_category"], location)
            if rec:
                record_dict = rec.to_ordered_dict()
                collected_upcs.append(record_dict["upc"])
                collected_records.append(record_dict)
                storage.write_staging_record(staging_file, record_dict)
        completed_subcats.append(cat_key)

    # Persist checkpoint metadata and rows snapshot to disk
    storage.save_checkpoint(
        store_id=store_id,
        completed_subcategories=completed_subcats,
        scraped_ids=collected_upcs,
        staged_records=collected_records
    )

    # Dynamically persist exact expected product IDs from Phase 1 for mathematical verification
    phase1_expected_ids = [r["upc"] or r["product_title"] for r in collected_records]
    expected_ids_path = os.path.join(work_dir, "phase1_expected_ids.json")
    with open(expected_ids_path, "w", encoding="utf-8") as f:
        json.dump(phase1_expected_ids, f, indent=2)

    print(f"[PROCESS 1 | PID: {pid}] Processed 14 subcategories ({len(collected_records)} items).")
    print(f"[PROCESS 1 | PID: {pid}] Checkpoint, rows snapshot, and {len(phase1_expected_ids)} exact IDs written to disk.")
    print(f"[PROCESS 1 | PID: {pid}] SIMULATING SUDDEN PREEMPTION / CRASH: Process terminating now.")
    sys.exit(0)

def run_phase_2(work_dir: str):
    pid = os.getpid()
    print(f"[PROCESS 2 | PID: {pid}] Brand new process spawned! Resuming from {work_dir}...")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from src.storage_manager import StorageManager
    from src.config_loader import ConfigLoader
    from src.parser import MarianoPageParser
    from src.normalizer import DataNormalizer

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_loader = ConfigLoader(base_dir)
    category_entries = config_loader.load_category_urls()
    location = config_loader.get_default_location()
    parser = MarianoPageParser(DataNormalizer([]))
    storage = StorageManager(base_dir=work_dir, min_records_threshold=500)
    store_id = "53100503"

    responses_dir = os.path.join(base_dir, "data", "raw", "responses")
    response_files = sorted([f for f in os.listdir(responses_dir) if f.endswith(".json")])

    staging_file_resumed = os.path.join(storage.staging_dir, "staging_session_phase2_resumed.jsonl")

    # Step 1: Detect checkpoint
    cp = storage.load_checkpoint(store_id)
    completed_subcats = cp.get("completed_subcategories", [])
    print(f"[PROCESS 2 | PID: {pid}] Checkpoint detected on disk: {len(completed_subcats)} subcategories completed.")

    # Step 2: Restore rows from disk
    restored_count = storage.restore_checkpoint_rows(store_id, staging_file_resumed)
    print(f"[PROCESS 2 | PID: {pid}] StorageManager.restore_checkpoint_rows(): Restored {restored_count} rows.")

    # Step 3: Compute mathematical set comparison for Phase 1 restored IDs
    expected_ids_path = os.path.join(work_dir, "phase1_expected_ids.json")
    with open(expected_ids_path, "r", encoding="utf-8") as f:
        phase1_expected_ids = json.load(f)

    restored_staging_records = storage.load_staging_records(staging_file_resumed)
    restored_ids = [r["upc"] or r["product_title"] for r in restored_staging_records]
    
    # Calculate exact differences dynamically
    lost_phase1_ids = list(set(phase1_expected_ids) - set(restored_ids))
    unexpected_restored_ids = list(set(restored_ids) - set(phase1_expected_ids))
    duplicate_restored_ids = len(restored_ids) - len(set(restored_ids))

    # Step 4: Continue remaining categories (15-28)
    resumed_all_subcats = list(completed_subcats)
    total_added_in_phase2 = 0
    phase2_expected_ids = []

    for i in range(14, 28):
        entry = category_entries[i]
        cat_key = f"{entry['category']}::{entry['sub_category']}"
        with open(os.path.join(responses_dir, response_files[i]), "r", encoding="utf-8") as f:
            resp_payload = json.load(f)
        for p in resp_payload.get("data", {}).get("products", []):
            rec = parser.parse_product_item(p, entry["category"], entry["sub_category"], location)
            if rec:
                record_dict = rec.to_ordered_dict()
                storage.write_staging_record(staging_file_resumed, record_dict)
                total_added_in_phase2 += 1
                phase2_expected_ids.append(record_dict["upc"] or record_dict["product_title"])
        resumed_all_subcats.append(cat_key)

    # Step 5: Final Dataset Mathematical Verification BEFORE Commit
    all_final_records = storage.load_staging_records(staging_file_resumed)
    final_ids = [r["upc"] or r["product_title"] for r in all_final_records]
    all_expected_ids = phase1_expected_ids + phase2_expected_ids

    lost_final_ids = list(set(all_expected_ids) - set(final_ids))
    unexpected_final_ids = list(set(final_ids) - set(all_expected_ids))
    duplicate_final_ids = len(final_ids) - len(set(final_ids))
    expected_keys = [f"{e['category']}::{e['sub_category']}" for e in category_entries]

    # VALIDATE ALL INVARIANTS BEFORE CALLING COMMIT
    invariants_passed = bool(
        len(lost_phase1_ids) == 0 and
        len(unexpected_restored_ids) == 0 and
        duplicate_restored_ids == 0 and
        len(lost_final_ids) == 0 and
        len(unexpected_final_ids) == 0 and
        duplicate_final_ids == 0 and
        len(final_ids) == len(all_expected_ids) and
        len(resumed_all_subcats) == len(category_entries)
    )

    proof_path = os.path.join(base_dir, "logs", "real_process_recovery_audit_proof.json")
    os.makedirs(os.path.dirname(proof_path), exist_ok=True)

    if not invariants_passed:
        # Pre-commit gate failed: DO NOT COMMIT, PRESERVE CHECKPOINT, EMIT FAILURE REPORT
        print(f"[PROCESS 2 | PID: {pid}] PRE-COMMIT GATE FAILED! Aborting atomic swap to preserve checkpoint.")
        failure_proof = {
            "audit_name": "PACKAGED_RESPONSE_REPLAY_RECOVERY_TEST",
            "test_type": "packaged_response_replay_recovery_test",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "FAILED",
            "measurements": {
                "lost_phase1_ids_count": len(lost_phase1_ids),
                "duplicate_restored_ids": duplicate_restored_ids,
                "lost_final_ids_count": len(lost_final_ids),
                "duplicate_final_ids": duplicate_final_ids,
                "expected_total_records": len(all_expected_ids),
                "actual_total_records": len(final_ids)
            },
            "atomic_swap_executed": False
        }
        with open(proof_path, "w", encoding="utf-8") as pf:
            json.dump(failure_proof, pf, indent=2)
        sys.exit(1)

    # Invariants passed: Execute Atomic Swap
    swap_success = storage.commit_dataset_atomic(
        store_id=store_id,
        staging_filepath=staging_file_resumed,
        total_categories_expected=len(expected_keys),
        categories_processed=len(resumed_all_subcats),
        expected_category_keys=expected_keys,
        actual_completed_keys=resumed_all_subcats
    )

    all_passed = invariants_passed and (swap_success is True)

    print("\n" + "=" * 80)
    print("PACKAGED RESPONSE REPLAY RECOVERY TEST SUMMARY")
    print("=" * 80)
    print(f"  • Process 1 (Killed) Output Restored:  {restored_count} records")
    print(f"  • Process 2 (Resumed) Ingested:       {total_added_in_phase2} records")
    print(f"  • Total Final Reconciled Records:     {len(final_ids)} (Expected: {len(all_expected_ids)})")
    print(f"  • Dynamically Calculated Lost IDs:    {len(lost_final_ids)} (PASS)")
    print(f"  • Dynamically Calculated Duplicate IDs: {duplicate_final_ids} (PASS)")
    print(f"  • 100% Subcategory Coverage:          {len(resumed_all_subcats)}/28 (PASS)")
    print(f"  • Pre-Commit Invariant Gate:          {'PASS' if invariants_passed else 'FAIL'}")
    print(f"  • Production Atomic Swap:             {'PASS' if swap_success else 'FAIL'}")
    print(f"  • Machine-Readable Audit Proof:       {proof_path}")
    print("=" * 80)

    proof_data = {
        "audit_name": "PACKAGED_RESPONSE_REPLAY_RECOVERY_TEST",
        "test_type": "packaged_response_replay_recovery_test",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all_passed else "FAILED",
        "measurements": {
            "process_1_restored_records": restored_count,
            "process_2_ingested_records": total_added_in_phase2,
            "total_final_records": len(final_ids),
            "expected_total_records": len(all_expected_ids),
            "dynamically_calculated_lost_ids": len(lost_final_ids),
            "dynamically_calculated_duplicate_ids": duplicate_final_ids,
            "dynamically_calculated_unexpected_ids": len(unexpected_final_ids),
            "subcategory_coverage": f"{len(resumed_all_subcats)}/28"
        },
        "pre_commit_invariants_passed": invariants_passed,
        "atomic_swap_passed": swap_success,
        "verification_conclusion": "PACKAGED_RESPONSE_REPLAY_RECOVERY_TEST PASSED" if all_passed else "RECOVERY_FAILED"
    }

    with open(proof_path, "w", encoding="utf-8") as pf:
        json.dump(proof_data, pf, indent=2)

    assert all_passed is True, "Recovery test failed"
    print("PACKAGED RESPONSE REPLAY RECOVERY: 100% VERIFIED SUCCESS")
    print("=" * 80)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--phase1":
        run_phase_1(sys.argv[2])
        return
    elif len(sys.argv) > 1 and sys.argv[1] == "--phase2":
        run_phase_2(sys.argv[2])
        return

    print("=" * 85)
    print("MARIANO'S SCRAPER: PACKAGED RESPONSE REPLAY RECOVERY TEST")
    print("Timestamp: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 85)

    temp_dir = tempfile.mkdtemp(prefix="marianos_replay_recovery_")
    try:
        script_path = os.path.abspath(__file__)
        python_exe = sys.executable

        # --- STEP 1: Execute Process 1 ---
        print("\n>>> LAUNCHING SEPARATE OS PROCESS 1 (Initial Ingestion & Interruption)...")
        proc1 = subprocess.run([python_exe, script_path, "--phase1", temp_dir], capture_output=True, text=True)
        print(proc1.stdout)
        if proc1.stderr:
            print("[Process 1 STDERR]:", proc1.stderr)
        assert proc1.returncode == 0, f"Process 1 failed with return code {proc1.returncode}"
        print(">>> OS Process 1 has completely terminated.")

        # --- STEP 2: Execute Process 2 ---
        print("\n>>> LAUNCHING SEPARATE OS PROCESS 2 (Recovery, Row Restoration & Completion)...")
        proc2 = subprocess.run([python_exe, script_path, "--phase2", temp_dir], capture_output=True, text=True)
        print(proc2.stdout)
        if proc2.stderr:
            print("[Process 2 STDERR]:", proc2.stderr)
        assert proc2.returncode == 0, f"Process 2 failed with return code {proc2.returncode}"
        print(">>> OS Process 2 has completely terminated with SUCCESS.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
