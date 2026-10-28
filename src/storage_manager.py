import os
import json
import shutil
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("MarianoScraper.Storage")

class StorageManager:
    """
    Manages atomic file swaps, checkpointing, resume capability,
    and guarantees that an incomplete or failed run never overwrites a good dataset for Mariano's.
    """

    def __init__(self, base_dir: Optional[str] = None, min_records_threshold: int = 500):
        if base_dir is None:
            self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        else:
            self.base_dir = os.path.abspath(base_dir)

        self.staging_dir = os.path.join(self.base_dir, "data", "staging")
        self.output_dir = os.path.join(self.base_dir, "data", "output")
        self.checkpoint_dir = os.path.join(self.base_dir, "data", "checkpoints")
        self.min_records_threshold = min_records_threshold

        for d in [self.staging_dir, self.output_dir, self.checkpoint_dir]:
            os.makedirs(d, exist_ok=True)

    def get_checkpoint_path(self, store_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_store_{store_id}.json")

    def load_checkpoint(self, store_id: str) -> Dict[str, Any]:
        """Loads completed categories and pages for resumption."""
        cp_path = self.get_checkpoint_path(store_id)
        if os.path.exists(cp_path):
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read checkpoint file {cp_path}: {e}")
        return {"completed_subcategories": [], "scraped_ids": []}

    def get_checkpoint_rows_path(self, store_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_rows_store_{store_id}.jsonl")

    def save_checkpoint(
        self,
        store_id: str,
        completed_subcategories: List[str],
        scraped_ids: List[str],
        staged_records: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Saves current state and completed rows to checkpoint files."""
        cp_path = self.get_checkpoint_path(store_id)
        temp_path = f"{cp_path}.tmp"
        data = {
            "store_id": store_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "completed_subcategories": completed_subcategories,
            "scraped_ids": list(set(scraped_ids))
        }
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        shutil.move(temp_path, cp_path)

        # Persist completed rows so subsequent runs can restore them
        if staged_records:
            rows_path = self.get_checkpoint_rows_path(store_id)
            rows_temp = f"{rows_path}.tmp"
            with open(rows_temp, "w", encoding="utf-8") as f:
                for r in staged_records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            shutil.move(rows_temp, rows_path)

    def restore_checkpoint_rows(self, store_id: str, current_staging_filepath: str) -> int:
        """
        Restores previously collected rows from an interrupted run into current staging.
        Performs strict ID-level deduplication to prevent duplicate rows across repeat resumes.
        """
        rows_path = self.get_checkpoint_rows_path(store_id)
        restored = 0
        if not os.path.exists(rows_path):
            return restored

        # Ingest existing IDs already present in current staging to prevent duplicates
        existing_keys = set()
        if os.path.exists(current_staging_filepath):
            for r in self.load_staging_records(current_staging_filepath):
                key = r.get("upc") or r.get("product_id") or r.get("product_title")
                if key:
                    existing_keys.add(key)

        with open(rows_path, "r", encoding="utf-8") as src, open(current_staging_filepath, "a", encoding="utf-8") as dst:
            for line in src:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                    key = record.get("upc") or record.get("product_id") or record.get("product_title")
                    if key and key in existing_keys:
                        # Skip already present row to guarantee idempotence
                        continue
                    if key:
                        existing_keys.add(key)
                    dst.write(line_str + "\n")
                    restored += 1
                except json.JSONDecodeError:
                    continue

        logger.info(
            f"[LOG-OBS: CARRIED_FORWARD_HISTORICAL] Restored {restored} unique previously collected rows "
            f"from checkpoint into {current_staging_filepath} (deduplicated against existing staging)."
        )
        return restored

    def clear_checkpoint(self, store_id: str) -> None:
        """Removes checkpoint file and persisted rows after a completely successful run."""
        cp_path = self.get_checkpoint_path(store_id)
        if os.path.exists(cp_path):
            os.remove(cp_path)
        rows_path = self.get_checkpoint_rows_path(store_id)
        if os.path.exists(rows_path):
            os.remove(rows_path)

    def write_staging_record(self, staging_filepath: str, record_dict: Dict[str, Any]) -> None:
        """Appends a single record to the staging file (JSON lines format)."""
        with open(staging_filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")

    def load_staging_records(self, staging_filepath: str) -> List[Dict[str, Any]]:
        """Reads all records accumulated in staging."""
        records = []
        if not os.path.exists(staging_filepath):
            return records
        with open(staging_filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def sync_to_azure_blob(self, local_filepath: str, blob_name: str) -> bool:
        """
        Uploads published dataset, raw evidence, or checkpoint to Azure Blob Storage container.
        Provides robust production cloud persistence with local filesystem fallback.
        """
        settings_path = os.path.join(self.base_dir, "config", "settings.json")
        azure_cfg = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    azure_cfg = json.load(f).get("safety_and_storage", {}).get("azure_blob_storage", {})
            except Exception:
                pass

        if not azure_cfg.get("enabled"):
            return False

        conn_str_env = azure_cfg.get("connection_string_env", "AZURE_STORAGE_CONNECTION_STRING")
        conn_str = os.environ.get(conn_str_env)
        container_name = azure_cfg.get("container_name", "marianos-scraped-data")

        try:
            from azure.storage.blob import BlobServiceClient
            if conn_str:
                blob_service = BlobServiceClient.from_connection_string(conn_str)
                container_client = blob_service.get_container_client(container_name)
                if not container_client.exists():
                    container_client.create_container()
                blob_client = container_client.get_blob_client(blob_name)
                with open(local_filepath, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                logger.info(f"SUCCESS: Uploaded {local_filepath} to Azure Blob Storage: {container_name}/{blob_name}")
                return True
        except ImportError:
            logger.info(f"Azure Storage SDK not installed locally; logged cloud persistence staging for {blob_name}")
        except Exception as e:
            logger.warning(f"Azure Blob sync exception: {e}; local production persistence preserved.")
        return False

    @staticmethod
    def get_product_identity_key(record: Dict[str, Any]) -> str:
        """
        Builds a stable product identity key using genuine source identifiers:
        1. Genuine UPC (if populated and not blank)
        2. Stable product URL (fallback if UPC is blank)
        3. Product ID or title + category fallback (if URL is also blank)
        Ensures items with empty UPC are never dropped during assortment retention.
        """
        upc = str(record.get("upc") or "").strip()
        if upc:
            return f"upc:{upc}"
        url = str(record.get("url") or "").strip().rstrip("/")
        if url:
            return f"url:{url}"
        pid = str(record.get("product_id") or record.get("id") or "").strip()
        if pid:
            return f"pid:{pid}"
        title = str(record.get("product_title") or "").strip().lower()
        cat = str(record.get("category") or "").strip().lower()
        subcat = str(record.get("sub_category") or "").strip().lower()
        if title:
            return f"title:{cat}:{subcat}:{title}"
        return f"raw:{hash(json.dumps(record, sort_keys=True))}"

    def merge_indefinite_store_assortment(
        self,
        fresh_records: List[Dict[str, Any]],
        existing_target_filepath: str
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Per Brief Requirement:
        'retain all unavailable store-assortment products indefinitely, including those with 
        no current pickup offer or price; keep carried observation dates/values distinct from fresh evidence.'
        
        Preserves historical products missing from fresh crawl while maintaining their original crawl_date.
        Uses a consistent genuine source-ID/URL fallback (never drops items with blank UPC).
        Fails safely if historical catalog cannot be read.
        """
        if not os.path.exists(existing_target_filepath):
            return fresh_records, 0

        try:
            with open(existing_target_filepath, "r", encoding="utf-8") as f:
                previous_records = json.load(f)
            if not isinstance(previous_records, list):
                logger.warning(f"Previous catalog at {existing_target_filepath} is not a valid list. Preserving fresh records safely.")
                return fresh_records, 0
        except Exception as e:
            logger.warning(f"Could not load previous catalog for assortment retention: {e}. Preserving fresh records safely.")
            return fresh_records, 0

        fresh_keys = {self.get_product_identity_key(r) for r in fresh_records}
        carried_forward = []

        for prev in previous_records:
            prev_key = self.get_product_identity_key(prev)
            if prev_key not in fresh_keys:
                # Retain unavailable store-assortment product indefinitely with original crawl_date & values intact
                carried_forward.append(prev)

        if carried_forward:
            logger.info(
                f"[LOG-OBS: ASSORTMENT_RETENTION] Retained {len(carried_forward)} unavailable store-assortment "
                f"products indefinitely from previous catalog (original crawl_dates preserved)."
            )

        merged = fresh_records + carried_forward
        return merged, len(carried_forward)

    def commit_dataset_atomic(
        self,
        store_id: str,
        staging_filepath: str,
        total_categories_expected: int,
        categories_processed: int,
        expected_category_keys: Optional[List[str]] = None,
        actual_completed_keys: Optional[List[str]] = None,
        require_cloud_sync: Optional[bool] = None
    ) -> bool:
        """
        Validates the run and performs an atomic swap to data/output/marianos_scraped_data_store_{store_id}_latest.json.
        CRITICAL RULE: Never overwrites last successful dataset with an empty or incomplete run.
        Enforces:
        - Minimum records threshold
        - Exact category set traversal (100% completion, rejecting unexpected/missing keys)
        - Unique product UPCs (zero duplicates)
        - Atomic temporary file swap with backup
        - Cloud synchronization gate (fails publication and preserves checkpoint if mandatory upload fails)
        """
        records = self.load_staging_records(staging_filepath)
        total_count = len(records)
        target_output = os.path.join(self.output_dir, f"marianos_scraped_data_store_{store_id}_latest.json")
        backup_output = os.path.join(self.output_dir, f"marianos_scraped_data_store_{store_id}_backup.json")

        logger.info(f"Validating dataset: {total_count} records collected. Categories processed: {categories_processed}/{total_categories_expected}")

        # Quality check: Ensure minimum records threshold is met
        if total_count < self.min_records_threshold:
            logger.error(
                f"ABORTING DATASET COMMIT: Record count ({total_count}) is below required "
                f"minimum threshold ({self.min_records_threshold}). Existing dataset will NOT be overwritten!"
            )
            return False

        # Category coverage check: Strictly require 100% traversal completion (zero missing categories allowed)
        if total_categories_expected > 0 and categories_processed < total_categories_expected:
            logger.error(
                f"ABORTING DATASET COMMIT: Incomplete category coverage ({categories_processed}/{total_categories_expected}). "
                f"All {total_categories_expected} expected subcategories must be fully completed before dataset publication!"
            )
            return False

        # Strict Exact Category Set Comparison against expected CSV categories
        if expected_category_keys:
            expected_set = set(expected_category_keys)

            if actual_completed_keys is not None:
                completed_set = set(actual_completed_keys)
                missing_traversed = expected_set - completed_set
                unexpected_traversed = completed_set - expected_set

                if missing_traversed:
                    logger.error(
                        f"ABORTING DATASET COMMIT: Incomplete traversal. Missing expected categories: {missing_traversed}. "
                        f"Exact set match required!"
                    )
                    return False
                if unexpected_traversed:
                    logger.error(
                        f"ABORTING DATASET COMMIT: Unknown/unexpected category keys in traversal: {unexpected_traversed}"
                    )
                    return False

            # Verify staged records contain no rogue/unknown category keys
            staged_categories = {f"{r.get('category')}::{r.get('sub_category')}" for r in records}
            unexpected_in_records = staged_categories - expected_set
            if unexpected_in_records:
                logger.error(
                    f"ABORTING DATASET COMMIT: Unknown/unexpected category keys detected in records: {unexpected_in_records}"
                )
                return False

            if actual_completed_keys is None:
                missing_categories = expected_set - staged_categories
                if missing_categories:
                    logger.error(
                        f"ABORTING DATASET COMMIT: Missing required categories in records: {missing_categories}. Exact set match required!"
                    )
                    return False

        # Duplicate product IDs check
        seen_upcs = set()
        for r in records:
            upc = r.get("upc")
            if upc:
                if upc in seen_upcs:
                    logger.error(f"ABORTING DATASET COMMIT: Duplicate product UPC detected: {upc}")
                    return False
                seen_upcs.add(upc)

        # Indefinite Store Assortment Retention:
        # Merge unavailable/unobserved products from previous catalog, retaining original crawl_date
        records, retained_count = self.merge_indefinite_store_assortment(records, target_output)
        total_count = len(records)

        # Safe Atomic Swap:
        # 1. Write the new dataset to a temporary file first
        temp_final = f"{target_output}.tmp"
        with open(temp_final, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

        # 2. Back up previous dataset if it exists
        if os.path.exists(target_output):
            try:
                shutil.copy2(target_output, backup_output)
                logger.info(f"Previous successful dataset backed up to {backup_output}")
            except Exception as e:
                logger.warning(f"Could not create backup of previous dataset: {e}")

        # 3. Replace target with new validated dataset atomically
        shutil.move(temp_final, target_output)
        logger.info(f"SUCCESS: New Mariano's production dataset committed atomically to {target_output} ({total_count} records)")

        # 4. Sync committed dataset to Azure Blob Storage if configured
        settings_path = os.path.join(self.base_dir, "config", "settings.json")
        azure_cfg = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    azure_cfg = json.load(f).get("safety_and_storage", {}).get("azure_blob_storage", {})
            except Exception:
                pass

        cloud_enabled = azure_cfg.get("enabled", False)
        mandatory_cloud_sync = require_cloud_sync if require_cloud_sync is not None else azure_cfg.get("require_cloud_sync_in_production", False)

        if mandatory_cloud_sync or cloud_enabled:
            sync_ok = self.sync_to_azure_blob(target_output, f"marianos_scraped_data_store_{store_id}_latest.json")
            if mandatory_cloud_sync and not sync_ok:
                logger.error(
                    "ABORTING DATASET COMMIT: Mandatory Azure cloud sync failed. "
                    "Rolling back atomic swap and preserving checkpoint for retry."
                )
                if os.path.exists(backup_output):
                    shutil.copy2(backup_output, target_output)
                elif os.path.exists(target_output):
                    os.remove(target_output)
                return False

        # Clear checkpoint on clean completion
        self.clear_checkpoint(store_id)
        return True

    def calculate_statistics(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates field-completeness, unique count, and category distributions
        for contest submission requirements.
        """
        total_records = len(records)
        if total_records == 0:
            return {"total_count": 0}

        category_counts: Dict[str, int] = {}
        unique_urls = set()
        duplicates_count = 0
        field_fill_counts: Dict[str, int] = {}

        ppm_examples = []
        volume_deal_examples = []
        digital_deal_examples = []
        no_deal_examples = []

        # List of required fields
        sample_keys = list(records[0].keys())
        for k in sample_keys:
            field_fill_counts[k] = 0

        for r in records:
            cat = r.get("category", "Unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1

            url = r.get("url", "")
            upc = r.get("upc", "")
            key = upc if upc else url
            if key in unique_urls:
                duplicates_count += 1
            else:
                unique_urls.add(key)

            for k in sample_keys:
                val = r.get(k, "")
                if val is not None and str(val).strip() != "":
                    field_fill_counts[k] += 1

            # Categorize deal examples for contest entry
            if r.get("ppm") and len(ppm_examples) < 3:
                ppm_examples.append(r)
            if r.get("volume_deals_description") and len(volume_deal_examples) < 3:
                volume_deal_examples.append(r)
            if r.get("digital_deals_description") and len(digital_deal_examples) < 3:
                digital_deal_examples.append(r)
            if not r.get("volume_deals_description") and not r.get("digital_deals_description") and len(no_deal_examples) < 3:
                no_deal_examples.append(r)

        completeness_pct = {
            k: round((count / total_records) * 100, 2)
            for k, count in field_fill_counts.items()
        }

        return {
            "total_records": total_records,
            "unique_records": len(unique_urls),
            "duplicate_records": duplicates_count,
            "category_distribution": category_counts,
            "field_completeness_percentages": completeness_pct,
            "examples": {
                "ppm": ppm_examples,
                "volume_deals": volume_deal_examples,
                "digital_deals": digital_deal_examples,
                "no_deals": no_deal_examples
            }
        }
