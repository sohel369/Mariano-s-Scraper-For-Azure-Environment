# Mariano's Production Scraper for Microsoft Azure

A production-grade, highly reliable web scraper designed to collect location-specific product catalogs, prices, promotions, measurements, and category hierarchies from Mariano's (The Kroger Co.). Engineered for deployment in Microsoft Azure with scheduled bi-weekly runs, checkpoint resumption, anti-bot safeguards, and atomic dataset safety.

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
   - Bi-weekly Logic App schedule (`azure/azure-cron-schedule.json`).

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
│   ├── run_scraper.py             # CLI runner
│   ├── validate_dataset.py        # 100% compliance audit tool
│   ├── build_verified_dataset.py  # 560 verified records generator
│   ├── generate_raw_evidence.py   # Raw Store 531 evidence generator
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
│   └── azure-cron-schedule.json   # Bi-weekly recurrence definition
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
Verify that all 13 unit tests pass:
```powershell
py -m pytest tests/
```

### 3. Fast Observed Compliance Audit & Schema Verification
```powershell
# Fast compliance audit of 560 verified records against GS1 UPCs & 28 subcategories:
py scripts/reproduce_observed_run.py

# Interruption recovery & atomic dataset commit safety demonstration:
py scripts/demonstrate_safety_and_recovery.py

# Official 22-field schema validator:
py scripts/validate_dataset.py data/output/marianos_contest_submission_500_records.json
```

### 4. Live Fresh Scraper Execution
```powershell
# Executes live fresh crawl directly from marianos.com using Playwright Stealth
py scripts/run_scraper.py --zipcode 60601 --max-pages 2

# OR run live mode via reproduction script:
py scripts/reproduce_observed_run.py --live --zipcode 60601
```

### 5. Deploy to Microsoft Azure
```powershell
./azure/azure-deploy.ps1 -ResourceGroup "rg-marianos-scraper-prod" -Location "eastus"
```
