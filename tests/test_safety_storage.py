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
