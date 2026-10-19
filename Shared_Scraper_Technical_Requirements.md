# Shared Scraper Technical Requirements Specification

This document details the shared architecture, data contracts, resilience mechanisms, and quality benchmarks required across all retail scraping pipelines for the downstream ingestion system.

---

## 1. Data Schema & Ingestion Contract

### 1.1 Strict JSON Field Order
All records emitted by the scraping pipeline must adhere strictly to the following 22-field sequence:
1. `zipcode`
2. `store_name`
3. `store_location`
4. `store_logo`
5. `store_brand`
6. `category`
7. `sub_category`
8. `product_title`
9. `weight`
10. `regular_price`
11. `sale_price`
12. `volume_deals_description`
13. `volume_deals_price`
14. `digital_deals_description`
15. `digital_deals_price`
16. `image_url`
17. `url`
18. `upc`
19. `gupc`
20. `ppm`
21. `unit_price`
22. `crawl_date`

### 1.2 Data Formatting Rules
* **No Null Values:** Missing or non-applicable values must be represented as empty strings (`""`), never `null` or `undefined`.
* **Numeric Price Formatting:** Prices must be cleaned of currency symbols and commas, formatted consistently as decimal numbers (e.g., `12.98`).
* **Downstream Reserved Fields:** 
  * `gupc` must remain an empty string (`""`). The scraper must never invent or hash a GUPC.
  * `unit_price` must remain an empty string (`""`). Unit pricing will be calculated downstream based on standardized units.
* **Price Per Measure (PPM):** Must be extracted verbatim as displayed (e.g., `$0.25/oz`, `$3.99/lb`). Do not compute or estimate missing values.
* **Approximate Weights:** Any product with weight designations matching `approx`, `approximately`, `est.`, or `estimated` must be excluded.
* **Store Brand (Private Label):** Must evaluate strictly to `"yes"` or `"no"`.

---

## 2. Fulfillment Context & Anti-Marketplace Rules

* **Local Store Affinity:** The scraper must guarantee that session cookies (`postalCode`, `storeIntent`, `assrtLocation`) and request affinity flags enforce the assigned local store pickup/in-store context throughout the entire crawling cycle.
* **Third-Party Marketplace Rejection:** Only items sold and fulfilled directly by Walmart (`sellerName: "Walmart.com"`) are acceptable. Marketplace seller items must be discarded.
* **Shipping-Only Exclusion:** Items only available via nationwide parcel shipping rather than local store fulfillment must be excluded.

---

## 3. Resilience, Anti-Bot & Atomic Safety

* **Checkpoints & Safe Resumption:** The scraper must persist completed subcategories and seen item IDs to allow seamless recovery from network drops or process interruptions.
* **Silent Blocking & Thin Result Detection:** Response payloads must be validated against known CAPTCHA signatures (PerimeterX / HUMAN Security). An alert must trigger if category yield drops below minimum thresholds.
* **Canary Product Verification:** Critical staple products (e.g. Great Value Whole Milk) must be validated in grocery runs to verify live shelf data.
* **Atomic Dataset Commits:** Staging datasets must only overwrite production datasets (`_latest.json`) if total records exceed the minimum requirement (500+) and category completeness exceeds 80%. Failed or empty runs must NEVER overwrite previous valid datasets.

---

## 4. Microsoft Azure Integration

* **Headless Container Execution:** Standardized Dockerfile based on official Playwright images.
* **Schedule:** Bi-weekly execution (Sunday and Wednesday at 04:00 UTC) triggered via Azure Logic App recurrence.
* **Secrets Management:** Credentials, proxy connection strings, and storage keys must be injected via environment variables (`WALMART_PROXY_URL`, `AZURE_STORAGE_CONNECTION_STRING`), never hardcoded in source control.
