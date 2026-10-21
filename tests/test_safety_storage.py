import os
import json
import pytest
from src.storage_manager import StorageManager

def test_atomic_swap_prevents_incomplete_overwrite(tmp_path):
    storage = StorageManager(base_dir=str(tmp_path), min_records_threshold=10)
    store_id = "531"
    
    # Setup initial good dataset with 15 records
    good_dataset_file = os.path.join(storage.output_dir, f"marianos_scraped_data_store_{store_id}_latest.json")
    good_records = [{"title": f"Good Item {i}"} for i in range(15)]
    with open(good_dataset_file, "w", encoding="utf-8") as f:
        json.dump(good_records, f)

    # Simulate an incomplete/thin run with only 3 records
    staging_file = os.path.join(storage.staging_dir, "staging_failed_run.jsonl")
    for i in range(3):
        storage.write_staging_record(staging_file, {"title": f"Incomplete Item {i}"})

    # Attempt atomic commit - MUST return False and refuse overwrite
    commit_success = storage.commit_dataset_atomic(
        store_id=store_id,
        staging_filepath=staging_file,
        total_categories_expected=5,
        categories_processed=2
    )

    assert commit_success is False

    # Verify original good dataset is completely intact and untouched!
    with open(good_dataset_file, "r", encoding="utf-8") as f:
        persisted = json.load(f)
    assert len(persisted) == 15
    assert persisted[0]["title"] == "Good Item 0"

def test_checkpoint_lifecycle(tmp_path):
    storage = StorageManager(base_dir=str(tmp_path))
    store_id = "531"

    # Save checkpoint
    storage.save_checkpoint(store_id, ["Dairy & Eggs::Milk"], ["UPC123"])
    
    # Load checkpoint
    cp = storage.load_checkpoint(store_id)
    assert "Dairy & Eggs::Milk" in cp["completed_subcategories"]
    assert "UPC123" in cp["scraped_ids"]

    # Clear checkpoint
    storage.clear_checkpoint(store_id)
    cp_after = storage.load_checkpoint(store_id)
    assert cp_after["completed_subcategories"] == []

def test_row_restoration_on_resume(tmp_path):
    storage = StorageManager(base_dir=str(tmp_path), min_records_threshold=10)
    store_id = "53100503"
    staging_file = os.path.join(storage.staging_dir, "staging_test_resume.jsonl")

    # Phase 1: write 7 rows before simulated interruption
    phase1_rows = [{"upc": f"01111000{i:04d}", "title": f"Product {i}"} for i in range(7)]
    for r in phase1_rows:
        storage.write_staging_record(staging_file, r)
    
    # Save checkpoint with rows snapshot
    storage.save_checkpoint(
        store_id=store_id,
        completed_subcategories=["Fresh Produce::Fresh Fruits"],
        scraped_ids=[r["upc"] for r in phase1_rows],
        staged_records=phase1_rows
    )

    # Phase 2: Fresh session restores rows
    fresh_staging = os.path.join(storage.staging_dir, "staging_fresh_resumed.jsonl")
    restored_count = storage.restore_checkpoint_rows(store_id, fresh_staging)
    assert restored_count == 7

    # Phase 3: Append 8 more rows after resume
    for i in range(7, 15):
        storage.write_staging_record(fresh_staging, {"upc": f"01111000{i:04d}", "title": f"Product {i}"})

    all_rows = storage.load_staging_records(fresh_staging)
    assert len(all_rows) == 15
    assert all_rows[0]["upc"] == "011110000000"
    assert all_rows[14]["upc"] == "011110000014"

def test_strict_100_percent_category_gate(tmp_path):
    storage = StorageManager(base_dir=str(tmp_path), min_records_threshold=10)
    store_id = "53100503"
    staging_file = os.path.join(storage.staging_dir, "staging_gate_test.jsonl")
    for i in range(15):
        storage.write_staging_record(staging_file, {"upc": f"01111000{i:04d}"})

    # Under strict 100% production gate, 4 out of 5 MUST FAIL
    commit_4_of_5 = storage.commit_dataset_atomic(
        store_id=store_id,
        staging_filepath=staging_file,
        total_categories_expected=5,
        categories_processed=4
    )
    assert commit_4_of_5 is False

    # Only 5 out of 5 (100%) succeeds
    commit_5_of_5 = storage.commit_dataset_atomic(
        store_id=store_id,
        staging_filepath=staging_file,
        total_categories_expected=5,
        categories_processed=5
    )
    assert commit_5_of_5 is True
