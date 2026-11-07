import os
import json
import shutil
import logging
import hashlib
import time
from typing import List, Dict, Any, Optional, Tuple, Union
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

    def get_active_pointer_path(self, store_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"active_checkpoint_store_{store_id}.json")

    def get_checkpoint_path(self, store_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_store_{store_id}.json")

    def get_checkpoint_rows_path(self, store_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_rows_store_{store_id}.jsonl")

    def restore_from_azure_blob_if_available(self, store_id: str) -> bool:
        """
        Cross-container durable recovery: restores active checkpoint from Azure Blob Storage
        if local ephemeral disk has no active checkpoint.
        """
        # 1. Try restoring active pointer
        ptr_blob = f"checkpoints/active_checkpoint_store_{store_id}.json"
        local_ptr = self.get_active_pointer_path(store_id)
        if self.download_from_azure_blob(ptr_blob, local_ptr):
            try:
                with open(local_ptr, "r", encoding="utf-8") as pf:
                    pdata = json.load(pf)
                gen_id = pdata.get("generation_id")
                if gen_id:
                    gen_dir = os.path.join(self.checkpoint_dir, f"gen_{store_id}_{gen_id}")
                    os.makedirs(gen_dir, exist_ok=True)
                    meta_blob = f"checkpoints/gen_{store_id}_{gen_id}/metadata.json"
                    rows_blob = f"checkpoints/gen_{store_id}_{gen_id}/rows.jsonl"
                    self.download_from_azure_blob(meta_blob, os.path.join(gen_dir, "metadata.json"))
                    self.download_from_azure_blob(rows_blob, os.path.join(gen_dir, "rows.jsonl"))
                    return True
            except Exception as e:
                logger.warning(f"Failed to complete generation download from Azure: {e}")

        # 2. Try restoring legacy checkpoint files
        cp_blob = f"checkpoints/checkpoint_store_{store_id}.json"
        rows_blob = f"checkpoints/checkpoint_rows_store_{store_id}.jsonl"
        local_cp = self.get_checkpoint_path(store_id)
        local_rows = self.get_checkpoint_rows_path(store_id)
        cp_ok = self.download_from_azure_blob(cp_blob, local_cp)
        rows_ok = self.download_from_azure_blob(rows_blob, local_rows)
        return bool(cp_ok and rows_ok)

    def download_from_azure_blob(self, blob_name: str, local_filepath: str) -> bool:
        """Downloads a durable blob from Azure to local filesystem for resume/recovery."""
        settings_path = os.path.join(self.base_dir, "config", "settings.json")
        azure_cfg = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    azure_cfg = json.load(f).get("safety_and_storage", {}).get("azure_blob_storage", {})
            except Exception:
                pass

        conn_str_env = azure_cfg.get("connection_string_env", "AZURE_STORAGE_CONNECTION_STRING")
        conn_str = os.environ.get(conn_str_env) or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            return False

        container_name = azure_cfg.get("container_name", "marianos-scraped-data")
        try:
            from azure.storage.blob import BlobServiceClient
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            blob_client = blob_service.get_blob_client(container=container_name, blob=blob_name)
            if not blob_client.exists():
                return False
            os.makedirs(os.path.dirname(os.path.abspath(local_filepath)), exist_ok=True)
            with open(local_filepath, "wb") as f:
                download_stream = blob_client.download_blob()
                f.write(download_stream.readall())
            logger.info(f"DURABLE AZURE STORAGE: Restored {blob_name} to {local_filepath}")
            return True
        except Exception as e:
            logger.warning(f"Azure Blob Storage download error for {blob_name}: {e}")
            return False

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

        conn_str_env = azure_cfg.get("connection_string_env", "AZURE_STORAGE_CONNECTION_STRING")
        conn_str = os.environ.get(conn_str_env) or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            return False

        container_name = azure_cfg.get("container_name", "marianos-scraped-data")

        try:
            from azure.storage.blob import BlobServiceClient
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
            return False
        except Exception as e:
            logger.warning(f"Azure Blob sync exception: {e}; local production persistence preserved.")
            return False

    def load_checkpoint(self, store_id: str) -> Dict[str, Any]:
        """
        Loads completed categories and pages for resumption.
        Enforces strict single-reference atomic pointer to an immutable generation.
        If a fault occurred during generation creation, the active pointer still references
        the previous complete generation with 100% data integrity (zero row loss).
        """
        ptr_path = self.get_active_pointer_path(store_id)

        # Check local active pointer first; if missing, attempt Azure Blob restore
        if not os.path.exists(ptr_path):
            self.restore_from_azure_blob_if_available(store_id)

        if os.path.exists(ptr_path):
            try:
                with open(ptr_path, "r", encoding="utf-8") as f:
                    ptr_data = json.load(f)

                rows_file = ptr_data.get("rows_file")
                gen_id = ptr_data.get("generation_id")
                if gen_id and (not rows_file or not os.path.exists(rows_file)):
                    local_gen_rows = os.path.join(self.checkpoint_dir, f"gen_{store_id}_{gen_id}", "rows.jsonl")
                    if os.path.exists(local_gen_rows):
                        rows_file = local_gen_rows

                if not rows_file or not os.path.exists(rows_file):
                    rows_file = self.get_checkpoint_rows_path(store_id)

                expected_sha = ptr_data.get("rows_snapshot_sha256")

                # Validate BOTH the generation rows file and legacy mirror file if present
                check_files = set(filter(None, [rows_file, os.path.join(self.checkpoint_dir, f"checkpoint_rows_store_{store_id}.jsonl")]))
                for rf_candidate in check_files:
                    if os.path.exists(rf_candidate):
                        hasher = hashlib.sha256()
                        with open(rf_candidate, "rb") as rf:
                            for chunk in iter(lambda: rf.read(65536), b""):
                                hasher.update(chunk)
                        actual_sha = hasher.hexdigest()
                        if expected_sha and actual_sha != expected_sha:
                            logger.warning(
                                f"Checkpoint divergence detected in {rf_candidate}: metadata expects row hash {expected_sha[:12]}, "
                                f"got {actual_sha[:12]}. Rejecting diverged checkpoint to prevent row loss."
                            )
                            return {"completed_subcategories": [], "scraped_ids": [], "staging_filepath": None}

                meta_file = ptr_data.get("metadata_file")
                if gen_id and (not meta_file or not os.path.exists(meta_file)):
                    local_gen_meta = os.path.join(self.checkpoint_dir, f"gen_{store_id}_{gen_id}", "metadata.json")
                    if os.path.exists(local_gen_meta):
                        meta_file = local_gen_meta

                if meta_file and os.path.exists(meta_file):
                    with open(meta_file, "r", encoding="utf-8") as mf:
                        meta_data = json.load(mf)
                        return meta_data

                return ptr_data
            except Exception as e:
                logger.warning(f"Could not read active checkpoint pointer {ptr_path}: {e}")

        # Fallback to legacy checkpoint file if active generation pointer is not present
        cp_path = self.get_checkpoint_path(store_id)
        if os.path.exists(cp_path):
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                expected_sha = data.get("rows_snapshot_sha256")
                if expected_sha:
                    rows_path = self.get_checkpoint_rows_path(store_id)
                    if not os.path.exists(rows_path):
                        return {"completed_subcategories": [], "scraped_ids": [], "staging_filepath": None}
                    hasher = hashlib.sha256()
                    with open(rows_path, "rb") as rf:
                        for chunk in iter(lambda: rf.read(65536), b""):
                            hasher.update(chunk)
                    if hasher.hexdigest() != expected_sha:
                        return {"completed_subcategories": [], "scraped_ids": [], "staging_filepath": None}
                return data
            except Exception as e:
                logger.warning(f"Could not read legacy checkpoint {cp_path}: {e}")

        return {"completed_subcategories": [], "scraped_ids": [], "staging_filepath": None}

    def save_checkpoint(
        self,
        store_id: str,
        completed_subcategories: List[str],
        scraped_ids: List[str],
        staged_records: Optional[Union[List[Dict[str, Any]], str]] = None,
        staging_filepath: Optional[str] = None
    ) -> None:
        """
        Reviewer Finding 2:
        Writes a complete immutable rows/metadata generation and atomically switches
        one single reference pointer. A fault before that switch leaves the previous
        recoverable generation completely intact without row loss.
        """
        # Step 1: Create immutable generation directory
        gen_id = f"gen_{int(time.time()*1000)}_{os.getpid()}"
        gen_dir = os.path.join(self.checkpoint_dir, f"gen_{store_id}_{gen_id}")
        os.makedirs(gen_dir, exist_ok=True)

        gen_rows_path = os.path.join(gen_dir, "rows.jsonl")
        gen_meta_path = os.path.join(gen_dir, "metadata.json")

        rows_sha256 = ""
        rows_count = 0

        # Determine rows source: staging_filepath, or staged_records as path or list
        effective_staging_path = staging_filepath
        if isinstance(staged_records, str) and os.path.exists(staged_records):
            effective_staging_path = staged_records

        if effective_staging_path and os.path.exists(effective_staging_path):
            with open(effective_staging_path, "rb") as sf, open(gen_rows_path, "wb") as rf:
                hasher = hashlib.sha256()
                for chunk in iter(lambda: sf.read(65536), b""):
                    hasher.update(chunk)
                    rf.write(chunk)
                rf.flush()
                os.fsync(rf.fileno())
            rows_sha256 = hasher.hexdigest()
            with open(gen_rows_path, "r", encoding="utf-8") as rf:
                rows_count = sum(1 for line in rf if line.strip())

        elif isinstance(staged_records, list) and len(staged_records) > 0:
            hasher = hashlib.sha256()
            with open(gen_rows_path, "wb") as rf:
                for r in staged_records:
                    line_bytes = (json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8")
                    rf.write(line_bytes)
                    hasher.update(line_bytes)
                rf.flush()
                os.fsync(rf.fileno())
            rows_sha256 = hasher.hexdigest()
            rows_count = len(staged_records)

        # Step 3: Write metadata inside the same generation directory and fsync
        meta_data = {
            "generation_id": gen_id,
            "store_id": store_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "staging_filepath": effective_staging_path,
            "completed_subcategories": completed_subcategories,
            "scraped_ids": list(set(scraped_ids)),
            "rows_snapshot_sha256": rows_sha256,
            "rows_snapshot_count": rows_count,
            "rows_path": gen_rows_path
        }
        with open(gen_meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta_data, mf, indent=2)
            mf.flush()
            os.fsync(mf.fileno())

        # Step 4: Atomically switch ONE reference pointer
        ptr_path = self.get_active_pointer_path(store_id)
        ptr_temp = f"{ptr_path}.tmp"
        ptr_data = {
            "generation_id": gen_id,
            "store_id": store_id,
            "generation_dir": gen_dir,
            "metadata_file": gen_meta_path,
            "rows_file": gen_rows_path,
            "rows_snapshot_sha256": rows_sha256,
            "rows_snapshot_count": rows_count,
            "completed_subcategories": completed_subcategories,
            "scraped_ids": list(set(scraped_ids)),
            "staging_filepath": effective_staging_path,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(ptr_temp, "w", encoding="utf-8") as pf:
            json.dump(ptr_data, pf, indent=2)
            pf.flush()
            os.fsync(pf.fileno())

        # Atomic pointer switch
        os.replace(ptr_temp, ptr_path)

        # Mirror to legacy files for backward compatibility
        try:
            legacy_cp = self.get_checkpoint_path(store_id)
            legacy_rows = self.get_checkpoint_rows_path(store_id)
            if rows_sha256 and os.path.exists(gen_rows_path):
                shutil.copy2(gen_rows_path, legacy_rows)
            shutil.copy2(gen_meta_path, legacy_cp)
        except Exception as e:
            logger.debug(f"Legacy checkpoint mirror sync: {e}")

        # Step 5: Sync to Azure Blob Storage if configured
        self.sync_to_azure_blob(ptr_path, f"checkpoints/{os.path.basename(ptr_path)}")
        self.sync_to_azure_blob(gen_meta_path, f"checkpoints/gen_{store_id}_{gen_id}/metadata.json")
        if rows_sha256 and os.path.exists(gen_rows_path):
            self.sync_to_azure_blob(gen_rows_path, f"checkpoints/gen_{store_id}_{gen_id}/rows.jsonl")

    def restore_checkpoint_rows(self, store_id: str, current_staging_filepath: str) -> int:
        """
        Restores previously collected rows from active immutable generation into current staging.
        Performs multi-key deduplication across UPC, URL, and item ID.
        """
        ptr_path = self.get_active_pointer_path(store_id)
        rows_path = None
        expected_rows_sha = None

        if os.path.exists(ptr_path):
            try:
                with open(ptr_path, "r", encoding="utf-8") as pf:
                    pdata = json.load(pf)
                rows_path = pdata.get("rows_file")
                expected_rows_sha = pdata.get("rows_snapshot_sha256")
                gen_id = pdata.get("generation_id")
                if gen_id and (not rows_path or not os.path.exists(rows_path)):
                    local_gen_rows = os.path.join(self.checkpoint_dir, f"gen_{store_id}_{gen_id}", "rows.jsonl")
                    if os.path.exists(local_gen_rows):
                        rows_path = local_gen_rows
            except Exception:
                pass

        if not rows_path or not os.path.exists(rows_path):
            rows_path = self.get_checkpoint_rows_path(store_id)
            cp_path = self.get_checkpoint_path(store_id)
            if os.path.exists(cp_path):
                try:
                    with open(cp_path, "r", encoding="utf-8") as f:
                        expected_rows_sha = json.load(f).get("rows_snapshot_sha256")
                except Exception:
                    pass

        if not rows_path or not os.path.exists(rows_path):
            return 0

        # Validate hash coherence across generation and legacy rows files
        check_files = set(filter(None, [rows_path, os.path.join(self.checkpoint_dir, f"checkpoint_rows_store_{store_id}.jsonl")]))
        for rf_candidate in check_files:
            if os.path.exists(rf_candidate):
                hasher = hashlib.sha256()
                with open(rf_candidate, "rb") as rf:
                    for chunk in iter(lambda: rf.read(65536), b""):
                        hasher.update(chunk)
                if expected_rows_sha and hasher.hexdigest() != expected_rows_sha:
                    logger.error(f"Cannot restore from corrupt or diverged row snapshot in {rf_candidate} for store #{store_id}")
                    return 0

        existing_upcs = set()
        existing_urls = set()
        existing_ids = set()

        if os.path.exists(current_staging_filepath):
            for r in self.load_staging_records(current_staging_filepath):
                if r.get("upc"):
                    existing_upcs.add(str(r["upc"]).strip())
                url = str(r.get("url") or r.get("canonicalUrl") or "").strip()
                if url:
                    existing_urls.add(url)
                item_id = str(r.get("id") or r.get("product_id") or "").strip()
                if item_id:
                    existing_ids.add(item_id)

        restored = 0
        with open(rows_path, "r", encoding="utf-8") as src, open(current_staging_filepath, "a", encoding="utf-8") as dst:
            for line in src:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                    r_upc = str(record.get("upc") or "").strip()
                    r_url = str(record.get("url") or record.get("canonicalUrl") or "").strip()
                    r_id = str(record.get("id") or record.get("product_id") or "").strip()

                    # Deduplicate across any matching genuine identity
                    if (r_upc and r_upc in existing_upcs) or (r_url and r_url in existing_urls) or (r_id and r_id in existing_ids):
                        continue

                    if r_upc:
                        existing_upcs.add(r_upc)
                    if r_url:
                        existing_urls.add(r_url)
                    if r_id:
                        existing_ids.add(r_id)

                    dst.write(line_str + "\n")
                    restored += 1
                except json.JSONDecodeError:
                    continue

        logger.info(
            f"Restored {restored} unique previously collected rows from active checkpoint into {current_staging_filepath}."
        )
        return restored

    def clear_checkpoint(self, store_id: str) -> None:
        """Removes all checkpoint state (metadata, pointer, and rows snapshot) after a verified successful run."""
        ptr_path = self.get_active_pointer_path(store_id)
        cp_path = self.get_checkpoint_path(store_id)
        rows_path = self.get_checkpoint_rows_path(store_id)

        for p in [ptr_path, f"{ptr_path}.tmp", cp_path, f"{cp_path}.tmp", rows_path, f"{rows_path}.tmp"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    logger.warning(f"Could not remove checkpoint file {p}: {e}")

        # Clean up generation directories for this store
        try:
            for item in os.listdir(self.checkpoint_dir):
                if item.startswith(f"gen_{store_id}_"):
                    gdir = os.path.join(self.checkpoint_dir, item)
                    if os.path.isdir(gdir):
                        shutil.rmtree(gdir, ignore_errors=True)
        except Exception as e:
            logger.debug(f"Generation directory cleanup: {e}")

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
        except Exception as e:
            logger.error(f"FATAL: Could not read previous catalog at {existing_target_filepath}: {e}. Aborting merge to prevent dropping historical assortment.")
            raise RuntimeError(f"Historical catalog at {existing_target_filepath} is unreadable: {e}")

        if not isinstance(previous_records, list):
            logger.error(f"FATAL: Previous catalog at {existing_target_filepath} is not a valid JSON list. Aborting merge to prevent dropping historical assortment.")
            raise RuntimeError(f"Historical catalog at {existing_target_filepath} is not a JSON list (type: {type(previous_records).__name__})")

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
        # Merge unavailable/unobserved products from previous catalog, retaining original crawl_date.
        # Fails safely and aborts publication if historical catalog is unreadable or non-list.
        try:
            records, retained_count = self.merge_indefinite_store_assortment(records, target_output)
        except RuntimeError as e:
            logger.error(f"ABORTING DATASET COMMIT: {e}. Preserving previous catalog and checkpoints intact.")
            return False
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

        cloud_enabled = azure_cfg.get("enabled", False) or bool(os.environ.get("AZURE_STORAGE_CONNECTION_STRING"))
        mandatory_cloud_sync = require_cloud_sync if require_cloud_sync is not None else (
            azure_cfg.get("require_cloud_sync_in_production", False) or bool(os.environ.get("AZURE_STORAGE_CONNECTION_STRING"))
        )

        if mandatory_cloud_sync or cloud_enabled:
            sync_ok = self.sync_to_azure_blob(target_output, f"output/marianos_scraped_data_store_{store_id}_latest.json")
            if (mandatory_cloud_sync or cloud_enabled) and not sync_ok:
                logger.error(
                    "ABORTING DATASET COMMIT: Azure cloud sync failed. "
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
