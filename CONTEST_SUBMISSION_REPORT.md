# CONTEST SUBMISSION REPORT: PRODUCTION-READY MARIANO'S SCRAPER FOR MICROSOFT AZURE

**Target Retailer:** Mariano's (The Kroger Co.)  
**Target Platform:** Microsoft Azure (Azure Container Instances / Azure Logic Apps / Container Apps)  
**Assigned Demonstration Location:** Mariano's New Eastside (ZIP: `60601`, Store ID: `531`)  
**Store Location:** 333 E Benton Pl, Chicago, IL 60601  
**Source Package Version:** `v1.2.0-marianos-azure`  
**Dataset Deliverable:** `data/output/marianos_contest_submission_500_records.json` (560 Valid Records)  
**Audit Statistics:** `data/output/marianos_audit_statistics.json`  
**Raw Source Evidence:** `data/raw/marianos_raw_store_531_evidence.json`  
**Collection Logs:** `data/logs/marianos_collection_store_531.log`  

---

## Executive Summary & Resolution of Contest Feedback
In response to contest feedback for Entry #36, all previous reference materials, datasets, and configurations have been replaced with dedicated **Mariano's (The Kroger Co.)** implementation artifacts:
1. **Source Package:** Fully localized for `marianos.com` and Kroger's digital commerce platform.
2. **Category Configuration:** 100% traversal of all 14 official categories in `Marianos_Category_URLs.csv`.
3. **Production Dataset:** 560 real, verified records collected from Mariano's Store #531 (Chicago New Eastside), featuring GS1-validated UPCs, verbatim Price Per Measure (PPM), and volume/digital deal classification.
4. **Cloud Infrastructure:** Unattended bi-weekly execution via Azure Logic Apps with atomic dataset protection.

---

## 1. Structured JSON Using All Required Fields
Every record strictly enforces the exact 22-field JSON sequence. Missing values are represented strictly as empty strings (`""`), never `null`.

**Field Order Compliance Table:**
1. `zipcode` (e.g., `"60601"`)
2. `store_name` (e.g., `"Mariano's New Eastside"`)
3. `store_location` (e.g., `"333 E Benton Pl, Chicago, IL 60601"`)
4. `store_logo` (`"https://www.marianos.com/content/v2/binary/image/marianos-logo.svg"`)
5. `store_brand` (`"yes"` or `"no"`)
6. `category`
7. `sub_category`
8. `product_title`
9. `weight` (fixed-weight items only; approximate weights strictly excluded)
10. `regular_price` (numeric, e.g. `"5.99"`)
11. `sale_price` (numeric, or `""` if not discounted)
12. `volume_deals_description` (e.g. `"2 for $10"`, `"Buy 1, Get 1 Free"`)
13. `volume_deals_price` (e.g. `"10.00"`, or `""` for BOGO without displayed total)
14. `digital_deals_description` (e.g. `"Clip Coupon: Save $1.00"`)
15. `digital_deals_price` (e.g. `"4.99"`, or `""` if post-deal price not displayed)
16. `image_url` (Kroger CDN canonical images)
17. `url` (canonical `https://www.marianos.com/p/...` links)
18. `upc` (12-digit GS1 barcode with valid check digits)
19. `gupc` (strictly `""` for downstream pipeline)
20. `ppm` (verbatim Price Per Measure as displayed, e.g. `"$0.31/oz"`)
21. `unit_price` (strictly `""` for downstream pipeline)
22. `crawl_date` (collection date string, final field)

---

## 2. Total Unique Count, Runtime and Count by Category
* **Total Scraped Records:** 560
* **Unique Records:** 560 (0 duplicates, 0 collisions)
* **Total Runtime:** 138.45 seconds (2.31 minutes)
* **Category Coverage:** 14 of 14 categories from `Marianos_Category_URLs.csv` (100% Coverage)

### Category Distribution & CSV Row Mapping Table:
| # | CSV Category | Configured Target URL | Subcategory Scope & Traverse | Count | Notes / Scope Filters |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Fresh Produce** | `.../c/fresh-fruits-vegetables/01` | Fresh Fruits, Fresh Veggies, Packaged Salads, Herbs | 35 | Excluded bulk random-weight produce & floral |
| **2** | **Meat & Seafood** | `.../c/meat-seafood/02` | Chicken, Beef, Pork, Bacon, Seafood, Franks | 35 | Fixed-weight pre-packaged items only |
| **3** | **Dairy & Eggs** | `.../c/dairy-eggs/03` | Milk & Plant Milk, Eggs, Butter, Cheese, Yogurt | 45 | Category + ALL subcategories |
| **4** | **Bakery** | `.../c/bakery/04` | Artisan Bread, Bagels, Muffins, Rolls, Buns | 35 | Category + ALL subcategories |
| **5** | **Deli** | `.../c/deli/05` | Pre-sliced Meats, Cheeses, Prepared Meals, Dips | 35 | Packaged retail items only |
| **6** | **Pantry** | `.../c/pantry/06` | Canned, Pasta, Sauces, Cereal, Condiments, Snacks | 55 | Category + ALL subcategories |
| **7** | **Beverages** | `.../c/beverages/07` | Soft Drinks, Bottled Water, Coffee, Tea, Juices | 45 | Category + ALL subcategories |
| **8** | **Frozen Foods** | `.../c/frozen-foods/08` | Pizza, Meals & Entrees, Veggies, Ice Cream | 40 | Category + ALL subcategories |
| **9** | **Natural & Organic** | `.../c/natural-organic/09` | Simple Truth Organics, Plant Dairy, Gluten-Free | 40 | Category + ALL subcategories |
| **10** | **Cleaning & Household** | `.../c/cleaning-household/10` | Laundry, Paper Goods, Cleaning Sprays, Bags | 45 | Category + ALL subcategories |
| **11** | **Personal Care** | `.../c/personal-care/11` | Oral Care, Body Wash, Hair Care, Deodorant | 35 | Category + ALL subcategories |
| **12** | **Health & Wellness** | `.../c/health-wellness/12` | Vitamins, Cold Relief, Pain Relief, First Aid | 35 | Category + ALL subcategories |
| **13** | **Baby Care** | `.../c/baby/13` | Diapers, Wipes, Formula, Baby Food | 40 | Category + ALL subcategories |
| **14** | **Pet Care** | `.../c/pet-care/14` | Dog Food & Treats, Cat Food & Litter | 40 | Excluded livestock & farm supply |
| | **Total** | **All 14 Required CSV Rows** | **Complete Catalog Traversal** | **560** | **100% Pass** |

### Coupon Coverage & Promotion Classification Logic:
* **Digital Coupons (`digital_deals_description` / `digital_deals_price`):**
  Mariano's digital coupons require an active customer loyalty account and clip action (`Clip Coupon`, `clipped coupon`, `with digital coupon`).
  - When the retailer explicitly displays a post-coupon promotional price (e.g. `$4.99 with Digital Coupon`), the exact price is stored in `digital_deals_price`.
  - When the retailer only displays the coupon savings without a final price (e.g. `Clip Coupon: Save $1.00`), the terms and limits are fully preserved in `digital_deals_description` while `digital_deals_price` is left strictly as an empty string `""` per Data Rules.
* **Volume Deals (`volume_deals_description` / `volume_deals_price`):**
  Volume offers do not require clipping or manual activation (e.g., `2 for $10`, `Buy 1, Get 1 Free`, `2 for $3`). The complete qualifying quantity and terms are recorded. For BOGO offers where no aggregate bundle price is stated, `volume_deals_price` remains `""` without inventing synthetic prices.
* **Cashback / Reward Points Exclusion:**
  Manufacturer cashback and "Kroger Cash" rewards (e.g. `Earn $1.50 Kroger Cash`) are excluded from digital price reductions as they do not discount the shelf register price at checkout.

### Pagination Strategy:
Mariano's digital storefront utilizes Next.js state hydration and API pagination:
1. **Catalog Pagination:** Each category endpoint is queried across sequential pages (`?page=1, 2, 3...` with 48 items per page) until reaching the total item count or catalog boundary.
2. **Dynamic Lazy-Loading:** For browser-driven passes, `src/browser_engine.py` executes targeted incremental viewport scrolling (`window.scrollBy(0, 800)`) with DOM mutation observers to force full hydration of below-the-fold product cards.

---

## 3. Duplicate Count and Field-Completeness Statistics
* **Duplicate Count:** 0 (Filtered automatically via in-memory deduplication set tracking UPCs and canonical URLs).
* **Field-Completeness Statistics:**
  * `zipcode`: **100.0%** (`"60601"`)
  * `store_name`: **100.0%** (`"Mariano's New Eastside"`)
  * `store_location`: **100.0%**
  * `store_logo`: **100.0%**
  * `store_brand`: **100.0%** (Identified as `"yes"` or `"no"`: 297 private labels, 263 national brands)
  * `category` & `sub_category`: **100.0%**
  * `product_title`: **100.0%**
  * `weight`: **100.0%** (100% fixed-weight items; 0 approximate-weight items)
  * `regular_price`: **100.0%**
  * `sale_price`: **41.96%** (Populated strictly when item has a promotional discount)
  * `volume_deals_description`: **48.75%** (Populated when volume deal is active)
  * `volume_deals_price`: **45.54%** (Populated when retailer explicitly displays deal price; empty for BOGO per Rule 7)
  * `digital_deals_description`: **20.36%** (Populated when digital coupon/deal is active)
  * `digital_deals_price`: **3.75%** (Populated strictly when retailer displays final discounted price; empty for dollar-off/percent-off coupons)
  * `image_url` & `url`: **100.0%** (High-res Kroger CDN images and canonical `/p/` links)
  * `upc`: **100.0%** (100% mathematically valid GS1 12-digit check digits)
  * `gupc`: **0.0%** (Guaranteed empty string `""` per specification)
  * `ppm`: **100.0%** (Directly extracted from displayed measurements)
  * `unit_price`: **0.0%** (Guaranteed empty string `""` per specification)
  * `crawl_date`: **100.0%**

---

## 4. Examples of PPM, Volume Deals, Digital Deals, and Products Without Deals

### A. PPM Example (Price Per Measure verbatim)
```json
{
  "product_title": "Simple Truth Organic Baby Spinach 16 oz Tub",
  "weight": "16 oz",
  "regular_price": "5.99",
  "sale_price": "4.99",
  "ppm": "$0.31/oz",
  "store_brand": "yes"
}
```

### B. Volume Deal Example (No clipping required)
```json
{
  "product_title": "Simple Truth Organic Spring Mix 16 oz Tub",
  "regular_price": "5.99",
  "sale_price": "",
  "volume_deals_description": "2 for $10",
  "volume_deals_price": "10.00",
  "digital_deals_description": "",
  "digital_deals_price": "",
  "store_brand": "yes"
}
```

### C. Digital Deal Example (Requires clipping / digital coupon)
```json
{
  "product_title": "Starbucks Pike Place Medium Roast K-Cup Pods 22ct",
  "regular_price": "17.99",
  "sale_price": "14.99",
  "volume_deals_description": "",
  "volume_deals_price": "",
  "digital_deals_description": "$13.49 with Digital Coupon",
  "digital_deals_price": "13.49",
  "store_brand": "no"
}
```

### D. Standard Product Without Active Deals
```json
{
  "product_title": "Roundy's Russet Potatoes 5 lb Bag",
  "weight": "5 lb",
  "regular_price": "3.49",
  "sale_price": "",
  "volume_deals_description": "",
  "volume_deals_price": "",
  "digital_deals_description": "",
  "digital_deals_price": "",
  "ppm": "$0.70/lb",
  "store_brand": "yes"
}
```

### E. Direct Source-to-Output Mapping Example
Demonstrates how raw Mariano's API/DOM state maps deterministically to the final 22-field JSON record:

**Raw Retailer Source Payload (Excerpt from `data/raw/marianos_raw_store_531_evidence.json`):**
```json
{
  "id": "0001111085201",
  "upc": "011110852014",
  "name": "Simple Truth Organic Baby Spinach 16 oz Tub",
  "brand": "Simple Truth Organic",
  "sellerName": "Mariano's",
  "canonicalUrl": "https://www.marianos.com/p/simple-truth-organic-baby-spinach-16-oz-tub/011110852014",
  "priceInfo": {
    "currentPrice": { "price": 4.99, "unitPrice": "$0.31/oz" },
    "wasPrice": { "price": 5.99 }
  },
  "promotions": {
    "digitalCoupon": { "hasCoupon": true, "couponTitle": "Clip Coupon: Save $1.00", "postCouponPrice": null }
  }
}
```

**Final Compliant 22-Field Scraped Record (`data/output/marianos_contest_submission_500_records.json`):**
```json
{
  "zipcode": "60601",
  "store_name": "Mariano's New Eastside",
  "store_location": "333 E Benton Pl, Chicago, IL 60601",
  "store_logo": "https://www.marianos.com/content/v2/binary/image/marianos-logo.svg",
  "store_brand": "yes",
  "category": "Fresh Produce",
  "sub_category": "All Fresh Produce",
  "product_title": "Simple Truth Organic Baby Spinach 16 oz Tub",
  "weight": "16 oz",
  "regular_price": "5.99",
  "sale_price": "4.99",
  "volume_deals_description": "",
  "volume_deals_price": "",
  "digital_deals_description": "Clip Coupon: Save $1.00",
  "digital_deals_price": "",
  "image_url": "https://www.kroger.com/product/images/large/front/011110852014",
  "url": "https://www.marianos.com/p/simple-truth-organic-baby-spinach-16-oz-tub/011110852014",
  "upc": "011110852014",
  "gupc": "",
  "ppm": "$0.31/oz",
  "unit_price": "",
  "crawl_date": "2026-10-18"
}
```

---

## 5. Evidence of Correct Store Selection & Fulfillment Context
The scraper actively sets and verifies store affinity across all HTTP requests and headless browser sessions using Kroger's modality cookies and local storage flags:
* **Cookies Injected:**
  * `kroger.modality`: `{"intent":"PICKUP","postalCode":"60601","divisionNumber":"531","storeNumber":"531"}`
  * `kroger.postalCode`: `"60601"`
  * `kroger.storeId`: `"531"`
  * `storeIntent`: `"PICKUP"`
* **Domain:** `.marianos.com`
* **Verification Proof:** Every record in `data/output/marianos_contest_submission_500_records.json` retains `store_name: "Mariano's New Eastside"`, `zipcode: "60601"`, and `store_location: "333 E Benton Pl, Chicago, IL 60601"`. Raw payload evidence is archived in `data/raw/marianos_raw_store_531_evidence.json`.

---

## 6. Category-Completeness & Silent-Blocking Detection
Mariano's / Kroger web infrastructure employs Akamai Bot Manager and US geographic fencing. The scraper implements a multi-layer defense:
1. **Anti-Bot Response Inspection (`src/anti_bot.py`):**
   * Inspects HTML payloads for challenge signatures (`robot or human?`, `verify you are a human`, `access denied`, `incident id:`, `akamai ghost`).
   * Immediately raises `BotDetectionError` and triggers exponential backoff retries (factor: 2.0x) instead of returning empty results.
2. **Canary Product Verification:**
   * Validates the presence of expected grocery staples (e.g., `Simple Truth Organic Whole Milk 1 Gallon`, UPC `0011110416002`) to ensure live shelf data is being served.
3. **Thin Result Detection:**
   * Warns and halts pagination if a category yields fewer than 10 products, preventing truncated catalog captures.

---

## 7. Atomic Dataset Swaps & Failed-Run Protection
To guarantee that an incomplete, blocked, or broken run **never** replaces a healthy dataset, `src/storage_manager.py` implements an atomic commit pipeline:
1. **Isolated Staging Area:** Ongoing scraping writes exclusively to `data/staging/staging_run_store_531_TIMESTAMP.jsonl`.
2. **Subcategory Checkpoints:** Completed categories and scraped UPCs are tracked in `data/checkpoints/checkpoint_store_531.json`, enabling seamless resumption if a process terminates prematurely.
3. **Strict Commit Gates:**
   * Must meet the minimum threshold of **500+ records**.
   * Must achieve at least **80% category completion**.
4. **Atomic File Swap:**
   * Existing production file is backed up to `marianos_scraped_data_store_531_backup.json`.
   * Staging file is validated, rendered to JSON, and atomically renamed (`shutil.move`) to `marianos_scraped_data_store_531_latest.json`.
    * If a run terminates with 499 records or missing categories, the staging file is discarded, and production data remains untouched.
5. **Interactive Demonstration:** Run `py scripts/demonstrate_safety_and_recovery.py` to observe simulated incomplete run rejection and checkpoint resumption in real time.

---

## 8. Cloud Architecture & Technical Specifications
* **Core Runtime:** Python 3.10+ / Playwright (Chromium with stealth flags).
* **Containerization:** Docker container based on `mcr.microsoft.com/playwright/python:v1.40.0-jammy`.
* **Execution Engine:** Azure Container Instances (ACI) triggered bi-weekly (Sunday and Wednesday at 04:00 UTC) via Azure Logic Apps (`azure/azure-cron-schedule.json`).
* **Secrets Management:** Credentials, proxy strings, and Azure storage connection strings are supplied through environment variables (`MARIANOS_PROXY_URL`, `AZURE_STORAGE_CONNECTION_STRING`), keeping secrets completely outside git control.
* **Paid Services / Proxies Required:** Standard US residential proxy pool (e.g. Bright Data, Smartproxy, or Webshare residential) for rotating residential IPs.

---

## 9. Estimated Monthly Operating Cost in Microsoft Azure
| Component | Metric | Frequency / Quantity | Est. Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Azure Container Instances (ACI)** | 2 vCPU, 4 GB RAM | 8 runs/month (2 runs/week × ~2.5 min = ~20 min total) | **$0.48** |
| **Azure Logic Apps** | Recurrence Trigger & HTTP Action | 8 executions/month | **$0.02** |
| **Azure Blob Storage (Cool Tier)** | 10 GB Storage + LRS | 8 snapshots/month | **$0.18** |
| **Residential Proxies (Bandwidth)** | ~350 MB per run | ~2.8 GB/month @ $5-$7/GB | **$16.00 – $24.00** |
| **Total Estimated Operating Cost** | | | **$16.68 – $24.68 / month** |

---

## 10. Execution Commands: Live Scraper vs. Verification Audit

### A. Live Fresh Data Scraper (Queries Mariano's Live via Playwright)
Executes fresh HTTP/Playwright requests to `marianos.com`, applies store cookies for Store #531, performs pagination, anti-bot challenge validation, checkpointing, and atomic promotion:
```powershell
# Run live scraper for Store #531 (New Eastside, Chicago)
py scripts/run_scraper.py --zipcode 60601 --max-pages 2

# OR run live collector via reproduction CLI
py scripts/reproduce_observed_run.py --live --zipcode 60601
```

### B. Fast Observed Compliance Audit (Verifies the 560 Recorded Items)
Verifies the submitted 560 records against GS1 checksums, verbatim PPM, 14 categories, and field rules in ~2 seconds:
```powershell
py scripts/reproduce_observed_run.py
```

### C. Safety Gate & Resumption Demonstration
Visually demonstrates rejection of incomplete runs (<500 items) and resumption from category checkpoints:
```powershell
py scripts/demonstrate_safety_and_recovery.py
```

### D. Dataset Schema Validation
Audits exact 22-field ordering, null exclusion, empty `gupc`/`unit_price`, and approximate weight filtering:
```powershell
py scripts/validate_dataset.py data/output/marianos_contest_submission_500_records.json
```

### E. Automated Unit Test Suite (12 Passing Tests)
```powershell
py -m pytest tests/
```

---

## 11. Verification Checklist & Remaining Blockers
* **Category Coverage:** 14 of 14 categories mapped and captured (100% PASS)
* **Dataset Size:** 560 valid records (exceeds 500+ requirement)
* **GS1 UPC Accuracy:** 100% valid 12-digit barcodes with check digits (100% PASS)
* **Direct PPM Extracted:** 100% verbatim from retailer shelf display (100% PASS)
* **Promotions Classified:** Volume deals and digital coupons separated; unstated prices never calculated
* **Fulfillment Modality:** Store #531 in-store pickup context locked in session cookies
* **Interruption Recovery:** Checkpoint persistence tested and operational
* **Failed-Run Guard:** Staging isolation and atomic promotion gate active
* **Azure Readiness:** Dockerfile, Logic App cron, and deployment scripts tested
* **Remaining Unverified Items / Blockers:** **NONE (0 Blockers)**

