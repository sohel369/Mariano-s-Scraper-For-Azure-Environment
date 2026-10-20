import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set, List

from .config_loader import ConfigLoader
from .normalizer import DataNormalizer
from .models import MarianoProductRecord
from .anti_bot import AntiBotDetector, BotDetectionError
from .storage_manager import StorageManager
from .parser import MarianoPageParser
from .browser_engine import BrowserEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MarianoScraper.Pipeline")

class MarianoProductionScraper:
    """
    Production Scraper orchestrating multi-location runs, stealth browser automation,
    checkpoint resumption, anti-bot safeguards, and atomic dataset swapping for Mariano's (Kroger).
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.config_loader = ConfigLoader(base_dir)
        self.settings = self.config_loader.load_settings()
        self.private_brands = self.config_loader.load_private_brands()
        self.proxies = self.config_loader.load_proxies()

        self.normalizer = DataNormalizer(self.private_brands)
        self.parser = MarianoPageParser(self.normalizer)
        self.anti_bot = AntiBotDetector(
            canary_product_id=self.settings.get("scraping", {}).get("canary_product_id", "0001111041600"),
            min_yield_threshold=self.settings.get("scraping", {}).get("min_items_threshold_warning", 10)
        )
        self.storage = StorageManager(
            base_dir=base_dir,
            min_records_threshold=self.settings.get("safety_and_storage", {}).get("min_successful_records_for_atomic_swap", 500)
        )

        self.browser_engine: Optional[BrowserEngine] = None

    def execute_run(self, zipcode: Optional[str] = None, max_pages_override: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a complete scraping run for the selected Mariano's store location.
        """
        start_time = time.time()
        
        # 1. Select Store Location
        if zipcode:
            location = self.config_loader.get_location_by_zip(zipcode)
            if not location:
                logger.warning(f"Zipcode {zipcode} not found in locations.json, falling back to default.")
                location = self.config_loader.get_default_location()
        else:
            location = self.config_loader.get_default_location()

        store_id = str(location.get("store_id", "53100503"))
        logger.info(
            f"INITIATING MARIANO'S RUN: Store={location.get('store_name')}, "
            f"ZIP={location.get('zipcode')}, ID={store_id}, Mode=In-Store/Pickup"
        )

        # 2. Setup Staging and Checkpoints
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        staging_filename = f"staging_run_store_{store_id}_{run_timestamp}.jsonl"
        staging_filepath = os.path.join(self.storage.staging_dir, staging_filename)

        checkpoint = self.storage.load_checkpoint(store_id)
        completed_subcategories: List[str] = checkpoint.get("completed_subcategories", [])
        seen_keys: Set[str] = set(checkpoint.get("scraped_ids", []))

        # Restore previously collected rows into the fresh staging session
        restored_count = self.storage.restore_checkpoint_rows(store_id, staging_filepath)
        total_records_collected = restored_count
        if restored_count > 0:
            logger.info(f"Restored {restored_count} previously verified rows into staging session.")

        # 3. Load Categories CSV
        category_entries = self.config_loader.load_category_urls()
        total_subcategories = len(category_entries)
        logger.info(f"Loaded {total_subcategories} subcategories from Category URLs CSV")

        # 4. Initialize Browser Engine with Location Context
        self.browser_engine = BrowserEngine(self.settings, self.proxies)
        self.browser_engine.start()
        self.browser_engine.set_store_location(location)

        scraping_cfg = self.settings.get("scraping", {})
        max_retries = scraping_cfg.get("max_retries_per_page", 3)
        backoff_factor = scraping_cfg.get("retry_backoff_factor", 2.0)

        processed_categories_count = len(completed_subcategories)

        try:
            for entry in category_entries:
                cat = entry["category"]
                sub_cat = entry["sub_category"]
                base_url = entry["url"]
                subcat_key = f"{cat}::{sub_cat}"

                if subcat_key in completed_subcategories:
                    logger.info(f"Resuming: Skipping already completed subcategory [{subcat_key}]")
                    continue

                logger.info(f"Scraping category: {cat} -> {sub_cat} ({base_url})")
                subcat_records_count = 0
                subcat_failed = False
                page_num = 1

                # Complete catalog traversal without artificial caps (bounded only by catalog boundary or debug override)
                while True:
                    if max_pages_override and page_num > max_pages_override:
                        logger.info(f"Debug override reached ({max_pages_override} pages) for {subcat_key}.")
                        break

                    page_url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
                    
                    html_content = ""
                    success = False

                    for attempt in range(1, max_retries + 1):
                        try:
                            html_content = self.browser_engine.fetch_page_content(page_url)
                            # Verify response for silent blocking / CAPTCHA
                            self.anti_bot.inspect_html(html_content, page_url)
                            success = True
                            break
                        except BotDetectionError as bde:
                            logger.error(f"Anti-bot triggered on {page_url} (attempt {attempt}/{max_retries}): {bde}")
                            time.sleep(backoff_factor * attempt)
                        except Exception as e:
                            logger.warning(f"Error fetching {page_url} (attempt {attempt}/{max_retries}): {e}")
                            time.sleep(backoff_factor * attempt)

                    if not success:
                        logger.error(f"Failed to fetch {page_url} after {max_retries} retries. Marking subcategory as incomplete for retry.")
                        subcat_failed = True
                        break

                    # Parse page records (preserves out-of-stock items, zero availability deletion)
                    page_records: List[MarianoProductRecord] = self.parser.parse_page(
                        html_content=html_content,
                        category=cat,
                        sub_category=sub_cat,
                        location_info=location,
                        seen_keys=seen_keys
                    )

                    # Check yield and thin response warning
                    self.anti_bot.check_yield(cat, sub_cat, len(page_records))

                    if not page_records:
                        logger.info(f"Catalog boundary reached on page {page_num} for {subcat_key}. Completed traversal.")
                        break

                    # Write to staging immediately
                    for r in page_records:
                        self.storage.write_staging_record(staging_filepath, r.to_ordered_dict())
                        total_records_collected += 1
                        subcat_records_count += 1

                    page_num += 1

                # Subcategory completion gate: Only mark complete if all pages succeeded
                if not subcat_failed:
                    completed_subcategories.append(subcat_key)
                    processed_categories_count += 1
                    
                    # Checkpoint progress and persist rows after each completed subcategory
                    staged_snapshot = self.storage.load_staging_records(staging_filepath)
                    self.storage.save_checkpoint(store_id, completed_subcategories, list(seen_keys), staged_snapshot)
                    logger.info(f"Completed {subcat_key}: {subcat_records_count} items. Total so far: {total_records_collected}")
                else:
                    logger.warning(f"Subcategory {subcat_key} had page failures. Not marking as complete; will retry on next run.")

        finally:
            if self.browser_engine:
                self.browser_engine.close()

        # 5. Finalize and Validate Dataset
        runtime_seconds = round(time.time() - start_time, 2)
        staging_records = self.storage.load_staging_records(staging_filepath)

        # Check Canary Product
        self.anti_bot.verify_canary_product(staging_records)

        # Atomic commit to production
        is_committed = self.storage.commit_dataset_atomic(
            store_id=store_id,
            staging_filepath=staging_filepath,
            total_categories_expected=total_subcategories,
            categories_processed=processed_categories_count
        )

        # Compute audit statistics
        stats = self.storage.calculate_statistics(staging_records)
        stats["runtime_seconds"] = runtime_seconds
        stats["store_id"] = store_id
        stats["zipcode"] = location.get("zipcode")
        stats["store_name"] = location.get("store_name")
        stats["atomic_commit_successful"] = is_committed
        stats["categories_processed"] = f"{processed_categories_count}/{total_subcategories}"

        logger.info(
            f"MARIANO'S RUN COMPLETE: {len(staging_records)} total records collected in {runtime_seconds}s. "
            f"Commit status: {is_committed}"
        )
        return stats
