# Mariano's Production Scraper for Microsoft Azure

A production-grade, highly reliable web scraper designed to collect location-specific product catalogs, prices, promotions, measurements, and category hierarchies from Mariano's (The Kroger Co.). Engineered for deployment in Microsoft Azure with scheduled twice-per-week runs (Sunday & Wednesday 04:00 UTC), checkpoint resumption, anti-bot safeguards, and atomic dataset safety.

---

## Key Features

1. **Strict Contest Specification Adherence:**
   - Enforces the exact 22-field JSON sequence.
   - Missing values are returned as empty strings (`""`), never `null`.
   - `gupc` and `unit_price` are guaranteed empty strings for downstream processing.
   - `ppm` (Price Per Measure) is extracted directly from Mariano's without modification.
   - Products with approximate weights (`approx`, `approximately`) are automatically excluded.
   - Identifies Mariano's / Kroger private-label brands (`store_brand: "yes"`).
2. **Deals Categorization:**
   - **Volume Deals:** Complete terms in `volume_deals_description`, promotional price in `volume_deals_price`.
   - **Digital Deals:** Complete terms in `digital_deals_description`, promotional price in `digital_deals_price`.
   - Excludes cashback / points rewards from immediate digital price reductions.
3. **Store & Fulfillment Precision:**
   - Multi-location support configured via `config/locations.json`.
   - Preserves local pickup / in-store fulfillment context (`kroger.modality`, `kroger.storeId`) throughout every run.
   - Filters out 3rd-party marketplace sellers and shipping-only offers.
4. **Resilience & Safe Storage:**
   - Checkpoint-based resumption (`data/checkpoints/`) after network interruptions.
   - Staging isolation (`data/staging/`) prevents incomplete runs from ever overwriting production data.
   - Detects silent blocking, Akamai / Kasada challenges, and thin result yields.
5. **Azure Cloud Ready:**
   - Docker containerization (`azure/Dockerfile`).
   - One-click deployment scripts (`azure-deploy.sh` and `azure-deploy.ps1`).
   - Twice-per-week Logic App schedule (`azure/azure-cron-schedule.json`).

---

## Directory Structure

```
marianos-scraper-azure/
├── config/
│   ├── settings.json              # Scraping delays, timeouts, thresholds
│   ├── locations.json             # Store locations (ZIP, store_id, address)
│   ├── proxies.json               # Residential proxy configuration
│   └── private_brands.json        # Kroger / Mariano's private labels list
├── data/
│   ├── input/
│   │   └── Marianos_Category_URLs.csv # Categories and target URLs
│   ├── output/                    # Final validated datasets
│   ├── logs/                      # Collection run execution logs (Store 53100503)
│   ├── staging/                   # Staging area for ongoing runs
│   ├── checkpoints/               # Resumption checkpoints
│   └── raw/                       # Raw API payload evidence (Store 53100503)
├── preview/
│   ├── index.html                 # Interactive catalog & audit dashboard
│   ├── presentation_board.html    # Contest presentation & proof showcase
│   └── dataset.js                 # 560 verified records datastore
├── src/
│   ├── config_loader.py           # Configuration manager
│   ├── models.py                  # 22-field Pydantic model with exact ordering
│   ├── normalizer.py              # Weight filter, price & deals classifier
│   ├── anti_bot.py                # Bot challenge & yield monitoring
│   ├── browser_engine.py          # Playwright stealth & store selector
│   ├── parser.py                  # State & DOM extractor
│   ├── storage_manager.py         # Atomic dataset swap & statistics
│   └── scraper.py                 # Core scraping orchestrator
├── scripts/
│   ├── run_scraper.py             # CLI runner (unbounded pagination, live store verification)
│   ├── validate_dataset.py        # Official 22-field compliance audit tool (0 nulls, strict schema)
│   ├── reconcile_source_to_output.py # Source-to-output 22-field lineage audit (560/560 verified, 0 mismatches)
│   ├── verify_checkpoint_integrity.py # Interruption & deduplicated row restoration verification
│   ├── verify_store_identity.py   # Response-based store identity & PICKUP modality verification (--live supported)
│   ├── diagnose_akamai_block.py   # Low-level TCP/TLS edge diagnostic for Akamai Bot Manager behavior
│   ├── build_verified_dataset.py  # Verified catalog builder
│   ├── generate_raw_evidence.py   # Raw Store 53100503 API payload evidence generator
│   └── reproduce_observed_run.py  # Turnkey observed run reproduction script
├── tests/
│   ├── test_models.py             # Schema & field order tests
│   ├── test_normalizer.py         # Deals, weights, & price tests
│   └── test_safety_storage.py     # Atomic swap & checkpoint tests
├── azure/
│   ├── Dockerfile                 # Playwright container image
│   ├── docker-compose.yml         # Container orchestrator
│   ├── azure-deploy.sh            # Linux/Mac Azure deployment
│   ├── azure-deploy.ps1           # Windows PowerShell Azure deployment
│   └── azure-cron-schedule.json   # Twice-per-week recurrence definition (Sun/Wed 04:00 UTC)
├── requirements.txt
├── CONTEST_SUBMISSION_REPORT.md   # Complete contest entry report
└── README.md
```

---

## Quick Start Guide

### 1. Installation
Ensure Python 3.10+ is installed:
```powershell
py -m pip install -r requirements.txt
playwright install chromium
```

### 2. Run Automated Test Suite
Verify that all 23 unit tests pass:
```powershell
py -m pytest tests/
```

### 3. Production Verification & Audit Commands
```powershell
# 1. 28-row parent category brief mapping audit:
py scripts/audit_category_route_mapping.py

# 2. Automated missing-route publication rejection gate proof:
py scripts/verify_missing_route_rejection.py

# 3. Store assortment retention & date separation lifecycle proof:
py scripts/verify_assortment_retention_lifecycle.py

# 4. Official 22-field schema validator on exact 500-record demo file:
py scripts/validate_dataset.py data/output/marianos_contest_submission_500_records.json

# 5. Official 22-field schema validator on full 560-record catalog:
py scripts/validate_dataset.py data/output/marianos_scraped_data_store_53100503_full_catalog.json

# 6. Source-to-Output Lineage Audit (100% 22-field match, 0 mismatches, 0 fallbacks):
py scripts/reconcile_source_to_output.py

# 7. Checkpoint Interruption & Deduplicated Row Restoration Audit:
py scripts/verify_checkpoint_integrity.py

# 8. Store Identity & PICKUP Modality Verification (Payload & Live network probe):
py scripts/verify_store_identity.py
py scripts/verify_store_identity.py --live

# 9. Akamai Edge Network Diagnostic:
py scripts/diagnose_akamai_block.py
```

### 4. Dedicated Azure Bounded Diagnostic Probe (Manual Single-Execution)
To execute the isolated, lightweight diagnostic probe with strict circuit breakers (max 20 records, max 3 requests, 60s deadline, challenge classifier, and auto-cleanup):
```powershell
# Run standalone manual probe:
py scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address "1720 N Milwaukee Ave, Vernon Hills, IL 60061" --zipcode 60061 --fulfillment-type PICKUP

# Deploy dedicated probe container in Azure (1 vCPU, 2.0 GB RAM, zero recurring triggers, auto-cleanup):
./azure/azure-deploy-bounded-probe.ps1
# On Linux/macOS:
./azure/azure-deploy-bounded-probe.sh
```

### 5. Live Fresh Scraper Execution
```powershell
# Executes live fresh crawl directly from marianos.com using Playwright Stealth
py scripts/run_scraper.py --zipcode 60061 --max-pages 2

# OR run live mode via reproduction script:
py scripts/reproduce_observed_run.py --live --zipcode 60061
```

### 6. Deploy Full Production Stack to Microsoft Azure
```powershell
./azure/azure-deploy.ps1 -ResourceGroup "rg-marianos-scraper-prod" -Location "eastus"
```
