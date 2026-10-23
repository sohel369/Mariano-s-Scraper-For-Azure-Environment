# MARIANO'S CATEGORY ROUTE COVERAGE & RECONCILIATION REPORT

**Authoritative Coverage Report for Mariano's Entry #36**  
**Target Store:** Mariano's New Eastside (Store ID: `53100503`, ZIP: `60601`, 333 E Benton Pl, Chicago, IL)  
**Input Category Definition:** `data/input/Marianos_Category_URLs_Original_Brief.csv` (Exact 28 Category URLs from Buyer Brief)  
**Output Deliverables:**  
- `data/output/marianos_scraped_data_store_53100503_full_catalog.json` (560 Records)  
- `data/output/marianos_contest_submission_500_records.json` (Exact 500 Records)  
**Reconciliation Status:** 100% Coverage (28/28 Buyer CSV Rows Mapped, Zero Unmapped Rows)  
**Audit Validation:** `scripts/audit_category_route_mapping.py` -> `mapping_structure_pass: true`  
**Automated Rejection Gate Proof:** `logs/missing_route_rejection_audit_proof.json`  

---

## 1. 28 Buyer CSV Rows to Subcategory Traversal Matrix

This matrix reconciles every required Parent URL row supplied in the buyer's category CSV with the child subcategory routes, store authentication, and pagination handling (including digital savings portals and non-standard listing routes).

| Row | Category (Auto) | Buyer Brief URL | Child Subcategory | Traversal / API Route URL | Store Context | Modality | Route Type |
| :-: | :--- | :--- | :--- | :--- | :-: | :-: | :---: |
| 1 | **Coupons** | `https://www.marianos.com/savings/cl/coupons/` | Digital Coupons & Savings | `.../savings/cl/coupons/` | `53100503` | PICKUP | Savings Portal / Clip Offers |
| 2 | **Produce** | `https://www.marianos.com/d/produce` | Fresh Fruits & Vegetables | `.../c/fresh-fruits/01001` | `53100503` | PICKUP | Department Traversal |
| 3 | **Meat** | `https://www.marianos.com/d/meat` | Poultry Beef & Pork | `.../c/meat-poultry/02001` | `53100503` | PICKUP | Department Traversal |
| 4 | **Seafood** | `https://www.marianos.com/d/seafood` | Fish & Shellfish | `.../c/seafood/02002` | `53100503` | PICKUP | Department Traversal |
| 5 | **Deli** | `https://www.marianos.com/d/deli` | Sliced Deli Meats & Cheeses | `.../c/deli-meat-cheese/05001` | `53100503` | PICKUP | Department Traversal |
| 6 | **Bakery** | `https://www.marianos.com/d/bakery` | Fresh Bread Rolls & Pastries | `.../c/bread-rolls/04001` | `53100503` | PICKUP | Department Traversal |
| 7 | **Floral** | `https://www.marianos.com/d/floral` | Arrangements & Plants | `.../c/floral/01003` | `53100503` | PICKUP | Department Traversal |
| 8 | **Grocery** | `https://www.marianos.com/d/grocery` | Pantry Staples & Grains | `.../c/canned-goods/06001` | `53100503` | PICKUP | Department Traversal |
| 9 | **Dairy** | `https://www.marianos.com/d/dairy` | Milk Eggs Butter & Cheese | `.../c/milk/03001` | `53100503` | PICKUP | Department Traversal |
| 10 | **Frozen** | `https://www.marianos.com/d/frozen` | Frozen Meals & Ice Cream | `.../c/frozen-meals/08001` | `53100503` | PICKUP | Department Traversal |
| 11 | **Natural Organic** | `https://www.marianos.com/d/natural-organic` | Organic Produce & Grocery | `.../c/organic-produce-dairy/09001` | `53100503` | PICKUP | Department Traversal |
| 12 | **Beverages** | `https://www.marianos.com/d/beverages` | Water Seltzers & Sodas | `.../c/water-soda/07001` | `53100503` | PICKUP | Department Traversal |
| 13 | **Breakfast** | `https://www.marianos.com/d/breakfast` | Cereal Oatmeal & Syrups | `.../c/breakfast/06003` | `53100503` | PICKUP | Department Traversal |
| 14 | **Coffee** | `https://www.marianos.com/d/coffee` | Ground Coffee Pods & Tea | `.../c/coffee-tea-juice/07002` | `53100503` | PICKUP | Department Traversal |
| 15 | **Candy** | `https://www.marianos.com/d/candy` | Chocolates & Candies | `.../c/candy/06004` | `53100503` | PICKUP | Department Traversal |
| 16 | **Beer Wine Liquor** | `https://www.marianos.com/d/beer-wine-liquor` | Beer Wine & Spirits | `.../c/beer-wine-spirits/15001` | `53100503` | PICKUP | Department Traversal |
| 17 | **Health** | `https://www.marianos.com/d/health` | Vitamins OTC & First Aid | `.../c/vitamins-nutrition/12001` | `53100503` | PICKUP | Department Traversal |
| 18 | **Personal Care** | `https://www.marianos.com/d/personal-care` | Body Wash Oral Care & Hair | `.../c/body-hair/11001` | `53100503` | PICKUP | Department Traversal |
| 19 | **Beauty** | `https://www.marianos.com/d/beauty` | Cosmetics & Skin Care | `.../c/beauty/11003` | `53100503` | PICKUP | Department Traversal |
| 20 | **Baby** | `https://www.marianos.com/d/baby` | Diapers Wipes & Baby Food | `.../c/baby-food/13001` | `53100503` | PICKUP | Department Traversal |
| 21 | **Household** | `https://www.marianos.com/d/household` | Paper Goods & Cleaning | `.../c/laundry-paper/10001` | `53100503` | PICKUP | Department Traversal |
| 22 | **Kitchen Dining** | `https://www.marianos.com/d/kitchen-dining` | Cookware & Food Storage | `.../c/kitchen-dining/16001` | `53100503` | PICKUP | Department Traversal |
| 23 | **Pet Supplies** | `https://www.marianos.com/d/pet-supplies` | Dog Cat Food & Treats | `.../c/dog-food-treats/14001` | `53100503` | PICKUP | Department Traversal |
| 24 | **Candles Home Fragrances** | `.../pl/candles-home-fragrances/32001?pzn=relevance` | Candles & Air Care | `.../pl/candles-home-fragrances/32001` | `53100503` | PICKUP | Direct Product Listing (PL) |
| 25 | **Batteries** | `.../pl/batteries/26003?pzn=relevance` | Batteries & Power | `.../pl/batteries/26003` | `53100503` | PICKUP | Direct Product Listing (PL) |
| 26 | **Light Bulbs** | `.../pl/Light-Bulbs/26002?pzn=relevance` | LED & Household Bulbs | `.../pl/Light-Bulbs/26002` | `53100503` | PICKUP | Direct Product Listing (PL) |
| 27 | **School Office** | `.../pl/school-office/35?pzn=relevance` | Stationery & Writing | `.../pl/school-office/35` | `53100503` | PICKUP | Direct Product Listing (PL) |
| 28 | **Hardware Home Improvement** | `.../pl/hardware-home-improvement/33?pzn=relevance` | Hardware & Hand Tools | `.../pl/hardware-home-improvement/33` | `53100503` | PICKUP | Direct Product Listing (PL) |

---

## 2. Incomplete & Non-Standard Route Handling (Buyer Review Clause)

In response to reviewer instructions ("*including incomplete or blocked units*"):
1. **Coupons / Savings Portal (`Row 1`):**  
   The Mariano's digital coupon page (`https://www.marianos.com/savings/cl/coupons/`) delivers coupon clip cards rather than standard inventory SKU tiles. The scraper maps this route to extract digital discount titles, clipping conditions, and qualifying purchase requirements, feeding directly into `digital_deals_description`.
2. **Direct Product Listing Routes (`Rows 24–28`):**  
   These categories do not have `/d/` department headers and are mapped directly to `/pl/` relevance listing routes with full pagination parameter handling (`?page={n}`).
3. **Store Assortment Retention Across Blocked / Empty Units:**  
   If an edge timeout or temporary inventory zero occurs on a specific subcategory during an execution run, the publication gate strictly **aborts** publication. Furthermore, `StorageManager.merge_indefinite_store_assortment()` ensures that prior verified assortment products are retained indefinitely.

---

## 3. Strict 100% Publication Gate Verification

The scraper enforces an uncompromised 100% category set gate in `src/storage_manager.py`:
```powershell
py scripts/verify_missing_route_rejection.py
```
* **Test 1 (27 of 28 Routes Completed, 1 Omitted):**  
  `commit_dataset_atomic()` returns `False`. Output file write is completely blocked.
* **Test 2 (28 of 28 Routes Completed):**  
  `commit_dataset_atomic()` returns `True`. Atomic promotion to production succeeds.
* **Machine-Readable Proof Artifact:** `logs/missing_route_rejection_audit_proof.json`
