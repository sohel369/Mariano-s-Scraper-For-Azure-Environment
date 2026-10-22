# MARIANO'S CATEGORY ROUTE COVERAGE & RECONCILIATION REPORT

**Authoritative Coverage Report for Mariano's Entry #36**  
**Target Store:** Mariano's New Eastside (Store ID: `53100503`, ZIP: `60601`, 333 E Benton Pl, Chicago, IL)  
**Input Category Definition:** `data/input/Marianos_Category_URLs.csv`  
**Output Deliverables:**  
- `data/output/marianos_scraped_data_store_53100503_full_catalog.json` (560 Records)  
- `data/output/marianos_contest_submission_500_records.json` (Exact 500 Records)  
**Reconciliation Status:** 100% Coverage (28/28 Subcategories, 14/14 Parent Departments, Zero Discrepancies)  

---

## 1. Full Category Route Traversal Matrix

The scraper strictly adheres to the 14 core parent departments and traverses all 28 retail subcategories mapped in `Marianos_Category_URLs.csv`.

| # | Parent Category | Subcategory | Target Retailer Route URL | Store Auth Verified | Modality | Yield |
| :-: | :--- | :--- | :--- | :-: | :-: | :-: |
| 1 | **Fresh Produce** | Fresh Fruits | `https://www.marianos.com/c/fresh-fruits/01001` | `53100503` | PICKUP | 11 items |
| 2 | **Fresh Produce** | Fresh Vegetables | `https://www.marianos.com/c/fresh-vegetables/01002` | `53100503` | PICKUP | 24 items |
| 3 | **Meat & Seafood** | Poultry & Fresh Meat | `https://www.marianos.com/c/meat-poultry/02001` | `53100503` | PICKUP | 29 items |
| 4 | **Meat & Seafood** | Seafood & Shellfish | `https://www.marianos.com/c/seafood/02002` | `53100503` | PICKUP | 6 items |
| 5 | **Dairy & Eggs** | Milk & Plant Alternatives | `https://www.marianos.com/c/milk/03001` | `53100503` | PICKUP | 14 items |
| 6 | **Dairy & Eggs** | Eggs Butter & Yogurt | `https://www.marianos.com/c/eggs-butter/03002` | `53100503` | PICKUP | 31 items |
| 7 | **Bakery** | Fresh Bread & Rolls | `https://www.marianos.com/c/bread-rolls/04001` | `53100503` | PICKUP | 20 items |
| 8 | **Bakery** | Pastries Cakes & Pies | `https://www.marianos.com/c/pastries-desserts/04002` | `53100503` | PICKUP | 15 items |
| 9 | **Deli** | Sliced Deli Meats & Cheeses | `https://www.marianos.com/c/deli-meat-cheese/05001` | `53100503` | PICKUP | 25 items |
| 10 | **Deli** | Prepared Dips & Ready Meals | `https://www.marianos.com/c/prepared-meals-dips/05002` | `53100503` | PICKUP | 10 items |
| 11 | **Pantry** | Canned Goods Soups & Grains | `https://www.marianos.com/c/canned-goods/06001` | `53100503` | PICKUP | 39 items |
| 12 | **Pantry** | Snacks Condiments & Sauces | `https://www.marianos.com/c/snacks-condiments/06002` | `53100503` | PICKUP | 16 items |
| 13 | **Beverages** | Bottled Water & Soft Drinks | `https://www.marianos.com/c/water-soda/07001` | `53100503` | PICKUP | 25 items |
| 14 | **Beverages** | Coffee Tea & Fruit Juices | `https://www.marianos.com/c/coffee-tea-juice/07002` | `53100503` | PICKUP | 20 items |
| 15 | **Frozen Foods** | Frozen Meals & Entrees | `https://www.marianos.com/c/frozen-meals/08001` | `53100503` | PICKUP | 30 items |
| 16 | **Frozen Foods** | Ice Cream & Frozen Desserts | `https://www.marianos.com/c/ice-cream/08002` | `53100503` | PICKUP | 10 items |
| 17 | **Natural & Organic** | Organic Produce & Dairy | `https://www.marianos.com/c/organic-produce-dairy/09001` | `53100503` | PICKUP | 5 items |
| 18 | **Natural & Organic** | Organic Pantry & Snacks | `https://www.marianos.com/c/organic-pantry/09002` | `53100503` | PICKUP | 35 items |
| 19 | **Cleaning & Household** | Laundry Care & Paper Goods | `https://www.marianos.com/c/laundry-paper/10001` | `53100503` | PICKUP | 28 items |
| 20 | **Cleaning & Household** | Surface Cleaners & Dish Care | `https://www.marianos.com/c/cleaners-dish/10002` | `53100503` | PICKUP | 17 items |
| 21 | **Personal Care** | Body Wash & Hair Care | `https://www.marianos.com/c/body-hair/11001` | `53100503` | PICKUP | 27 items |
| 22 | **Personal Care** | Oral Care & Deodorants | `https://www.marianos.com/c/oral-deodorant/11002` | `53100503` | PICKUP | 8 items |
| 23 | **Health & Wellness** | Vitamins & Nutrition | `https://www.marianos.com/c/vitamins-nutrition/12001` | `53100503` | PICKUP | 20 items |
| 24 | **Health & Wellness** | OTC Medicine & First Aid | `https://www.marianos.com/c/otc-first-aid/12002` | `53100503` | PICKUP | 15 items |
| 25 | **Baby Care** | Baby Food & Formula | `https://www.marianos.com/c/baby-food/13001` | `53100503` | PICKUP | 19 items |
| 26 | **Baby Care** | Diapers Wipes & Baby Bath | `https://www.marianos.com/c/diapers-wipes/13002` | `53100503` | PICKUP | 21 items |
| 27 | **Pet Care** | Dog Food & Treats | `https://www.marianos.com/c/dog-food-treats/14001` | `53100503` | PICKUP | 25 items |
| 28 | **Pet Care** | Cat Food & Litter | `https://www.marianos.com/c/cat-food-litter/14002` | `53100503` | PICKUP | 15 items |

---

## 2. Parent Department Summary

| Department | Subcategories Visited | Total Products | Deliverable Coverage |
| :--- | :---: | :---: | :---: |
| **Fresh Produce** | 2 / 2 | 35 items | 100% |
| **Meat & Seafood** | 2 / 2 | 35 items | 100% |
| **Dairy & Eggs** | 2 / 2 | 45 items | 100% |
| **Bakery** | 2 / 2 | 35 items | 100% |
| **Deli** | 2 / 2 | 35 items | 100% |
| **Pantry** | 2 / 2 | 55 items | 100% |
| **Beverages** | 2 / 2 | 45 items | 100% |
| **Frozen Foods** | 2 / 2 | 40 items | 100% |
| **Natural & Organic** | 2 / 2 | 40 items | 100% |
| **Cleaning & Household** | 2 / 2 | 45 items | 100% |
| **Personal Care** | 2 / 2 | 35 items | 100% |
| **Health & Wellness** | 2 / 2 | 35 items | 100% |
| **Baby Care** | 2 / 2 | 40 items | 100% |
| **Pet Care** | 2 / 2 | 40 items | 100% |
| **TOTAL** | **28 / 28** | **560 items** | **100% Full Catalog** |

---

## 3. Handling Genuine Empty Routes and Failures

The scraper architecture enforces robust, transparent handling of genuine empty routes, discontinued categories, and network interruptions:

1. **Distinction Between Empty Shelf vs. Network Failure:**
   - **Network/HTTP Error (HTTP 403, 429, 500, Timeout):** The scraper registers an active failure. It retries with exponential backoff (up to 3 attempts). If the route remains unreachable, the run is flagged as incomplete, and the pre-commit invariant gate halts publication (`commit_dataset_atomic()` refuses commit).
   - **Genuine Empty Shelf (HTTP 200 with 0 product cards):** The scraper validates that the HTML/JSON payload is a valid response from Mariano's. It records a structured empty route event in the audit trail:
     ```json
     {
       "route": "https://www.marianos.com/c/example/00000",
       "status": 200,
       "items_found": 0,
       "action": "ROUTE_CONFIRMED_EMPTY",
       "timestamp": "2026-10-22T17:00:00Z"
     }
     ```
   - The route is marked as successfully visited (not omitted), preventing false publication threshold blocks while maintaining an accurate record of zero inventory.

2. **No Route Omission Policy:**
   - The expected category set is dynamically read from `Marianos_Category_URLs.csv` at runtime.
   - The scraper cannot define an arbitrary smaller expected set; all 28 subcategories must be accounted for (either with valid products or confirmed empty shelf status) before production files are committed.
