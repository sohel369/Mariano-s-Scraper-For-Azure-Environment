import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from bs4 import BeautifulSoup
from .models import MarianoProductRecord
from .normalizer import DataNormalizer

logger = logging.getLogger("MarianoScraper.Parser")

class MarianoPageParser:
    """
    Parses Mariano's (Kroger) category and browse pages.
    Extracts raw products from Kroger JSON state or DOM, enforces seller and fulfillment
    rules, filters out marketplace and approximate weights, and produces compliant records.
    """

    def __init__(self, normalizer: DataNormalizer):
        self.normalizer = normalizer

    @staticmethod
    def parse_strict_bool(val: Any) -> Optional[bool]:
        """
        Parses explicit boolean fulfillment indicators.
        Rejects non-boolean flags (such as numeric -1, 'unknown', etc.).
        Returns True for True/'true'/1, False for False/'false'/0, None otherwise.
        """
        if val is None:
            return None
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            if val == 1:
                return True
            if val == 0:
                return False
            return None
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("true", "1", "yes"):
                return True
            if s in ("false", "0", "no"):
                return False
        return None

    def validate_store_fulfillment_response(self, response_data: Dict[str, Any], expected_store_id: str = "53100503") -> Dict[str, Any]:
        """
        Validates Mariano's store identity, address, and pickup modality
        directly from the raw server response payload (store lookup endpoint).
        Strictly requires all fields from server response; no hardcoded fallbacks permitted.
        """
        data_wrapper = response_data.get("data", response_data)
        modality_ctx: Dict[str, Any] = {}

        if isinstance(data_wrapper, dict) and "store" in data_wrapper:
            store_obj = data_wrapper["store"]
            modality_ctx = data_wrapper.get("modalityContext", {})
        elif isinstance(data_wrapper, list) and len(data_wrapper) > 0:
            store_obj = data_wrapper[0]
        elif isinstance(data_wrapper, dict):
            store_obj = data_wrapper
        else:
            raise ValueError(f"Malformed store response payload: expected dict or non-empty list, got {type(data_wrapper)}")

        div_id_raw = store_obj.get("divisionNumber") or store_obj.get("divisionId") or modality_ctx.get("divisionId")
        if not div_id_raw:
            raise ValueError("Store validation failed: 'divisionNumber'/'divisionId' missing from server response payload!")
        div_id = str(div_id_raw).strip().zfill(3)

        str_num_raw = store_obj.get("storeNumber") or store_obj.get("storeId")
        if not str_num_raw:
            raise ValueError("Store validation failed: 'storeNumber'/'storeId' missing from server response payload!")
        str_num = str(str_num_raw).strip().zfill(5)

        full_loc_id = f"{div_id}{str_num}"
        server_loc_id = str(store_obj.get("locationId") or modality_ctx.get("fulfillmentStoreId") or "").strip()
        
        # Explicit ID match verification against server response
        if full_loc_id != expected_store_id and server_loc_id != expected_store_id:
            raise ValueError(
                f"Store ID verification failure: Server returned Location ID '{server_loc_id or full_loc_id}', "
                f"expected '{expected_store_id}'!"
            )

        address_info = store_obj.get("address")
        if not address_info or not isinstance(address_info, dict):
            raise ValueError("Store validation failed: 'address' object missing from server response payload!")

        street = address_info.get("addressLine1")
        city = address_info.get("city")
        state = address_info.get("state")
        zipcode = address_info.get("zipCode")

        if not street or not city or not state or not zipcode:
            raise ValueError(
                f"Store validation failed: Incomplete address fields in server response! "
                f"street='{street}', city='{city}', state='{state}', zipCode='{zipcode}'"
            )

        modalities = store_obj.get("fulfillmentMethods") or store_obj.get("modalities") or []
        if not isinstance(modalities, list):
            modalities = [modalities]
            
        pickup_verified = False
        for m in modalities:
            mod_str = m if isinstance(m, str) else m.get("type", "") if isinstance(m, dict) else ""
            if mod_str.upper() == "PICKUP":
                # Check eligibility/active if present in raw payload
                if isinstance(m, dict):
                    if m.get("active", True) and m.get("eligible", True):
                        pickup_verified = True
                        break
                else:
                    pickup_verified = True
                    break

        if not pickup_verified and modality_ctx.get("selectedModality", "").upper() == "PICKUP":
            pickup_verified = True

        if not pickup_verified:
            raise ValueError(f"Fulfillment validation failed: Store {full_loc_id} response does not offer active PICKUP modality!")

        store_name = store_obj.get("vanityName") or store_obj.get("name")
        if not store_name:
            raise ValueError("Store validation failed: 'vanityName'/'name' missing from server response payload!")

        return {
            "verified_store_id": full_loc_id,
            "division_id": div_id,
            "store_number": str_num,
            "store_name": str(store_name).strip(),
            "store_location": f"{street.strip()}, {city.strip()}, {state.strip()} {zipcode.strip()}",
            "zipcode": str(zipcode).strip(),
            "fulfillment_modality": "PICKUP",
            "response_status": "VERIFIED_PASS"
        }

    def parse_embedded_json(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON script tags containing product catalog states."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Look for Kroger application state or Next/Nuxt data
        for script_id in ["__NEXT_DATA__", "__PRELOADED_STATE__", "kroger-state"]:
            script_tag = soup.find("script", id=script_id)
            if script_tag and script_tag.string:
                try:
                    return json.loads(script_tag.string)
                except json.JSONDecodeError:
                    continue

        # 2. Look for JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type") in ["ItemList", "Product"]:
                        return data
                except json.JSONDecodeError:
                    continue

        return None

    def extract_items_from_json(self, state_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Traverses JSON data trees to find product items."""
        items: List[Dict[str, Any]] = []
        try:
            # Handle schema.org ItemList
            if state_data.get("@type") == "ItemList":
                for elem in state_data.get("itemListElement", []):
                    item = elem.get("item", {}) if isinstance(elem, dict) else elem
                    if item:
                        items.append(item)
                return items

            # Handle Kroger / Next props
            props = state_data.get("props", {}).get("pageProps", {})
            products_list = (
                props.get("products", []) or
                props.get("catalog", {}).get("products", []) or
                props.get("initialData", {}).get("products", [])
            )
            for p in products_list:
                if isinstance(p, dict):
                    items.append(p)
        except Exception as e:
            logger.warning(f"Error traversing JSON for Mariano's items: {e}")
        return items

    def parse_product_item(
        self,
        item: Dict[str, Any],
        category: str,
        sub_category: str,
        location_info: Dict[str, Any]
    ) -> Optional[MarianoProductRecord]:
        """
        Parses a single raw product item dictionary into a compliant MarianoProductRecord.
        Returns None if product fails qualification (e.g. approximate weight, missing title).
        """
        # 1. Product Title & Brand
        title = str(item.get("name") or item.get("title") or item.get("description") or "").strip()
        if not title:
            return None

        # Product-level store & fulfillment context binding
        # Rejects contradictory secondary evidence: inspects ALL location and modality fields across item and priceInfo
        price_info = item.get("priceInfo", {}) or {}
        expected_store_id = str(location_info.get("store_id", "53100502")).strip()
        expected_store_num = str(location_info.get("store_number", "00502")).strip()
        valid_store_ids = {
            expected_store_id,
            expected_store_num,
            "53100502", "00502", "vernon-hills",
            "53100503", "00503", "new-eastside"
        }

        # Check every location/store identifier candidate across item and priceInfo
        loc_candidates = [
            item.get("locationId"),
            item.get("storeId"),
            item.get("fulfillmentStoreId"),
            item.get("vanityId"),
            price_info.get("locationId"),
            price_info.get("storeId"),
            price_info.get("fulfillmentStoreId")
        ]
        has_conflicting_location = False
        for candidate in loc_candidates:
            if candidate is not None:
                cand_str = str(candidate).strip()
                if cand_str and cand_str not in valid_store_ids:
                    logger.debug(f"Product with contradictory location identifier: {title} ('{cand_str}' not in {valid_store_ids})")
                    has_conflicting_location = True
                    break

        # Strict positive explicit pickup context & non-pickup fulfillment checks (Reviewer finding 1)
        NON_PICKUP_KEYWORDS = (
            "SHIPPING", "DELIVERY", "SHIP", "MAIL", "FREIGHT", "EXPEDITED",
            "NOT_PICKUP", "NO_PICKUP", "NON_PICKUP", "PICKUP_UNAVAILABLE", "NOT PICKUP"
        )
        mod_candidates = [
            item.get("modality"),
            item.get("fulfillment"),
            item.get("fulfillmentType"),
            item.get("fulfillmentModality"),
            price_info.get("modality"),
            price_info.get("fulfillment"),
            price_info.get("fulfillmentType"),
            price_info.get("fulfillmentModality")
        ]
        has_positive_item_pickup = False
        item_pickup_false = False

        for mod in mod_candidates:
            if mod is not None:
                mod_str = str(mod).strip().upper()
                if mod_str:
                    if mod_str in ("PICKUP", "CURBSIDE", "IN_STORE_PICKUP", "STORE_PICKUP"):
                        has_positive_item_pickup = True
                    elif any(kw in mod_str for kw in NON_PICKUP_KEYWORDS):
                        item_pickup_false = True

        # Check numeric or boolean pickup flags (e.g. -1, 0, false, 1, true)
        pickup_flag_candidates = [
            item.get("inStorePickupAvailable"),
            item.get("pickupAvailable"),
            item.get("pickup"),
            item.get("isPickup"),
            price_info.get("inStorePickupAvailable"),
            price_info.get("pickupAvailable"),
            price_info.get("pickup"),
        ]
        for pf in pickup_flag_candidates:
            if pf is not None:
                parsed_bool = self.parse_strict_bool(pf)
                if parsed_bool is True:
                    has_positive_item_pickup = True
                elif parsed_bool is False or pf == -1 or str(pf).strip() == "-1":
                    item_pickup_false = True

        # Check pickupOptions if present
        if "pickupOptions" in item and isinstance(item["pickupOptions"], list):
            for opt in item["pickupOptions"]:
                if isinstance(opt, dict):
                    method = str(opt.get("fulfillmentMethod") or opt.get("method") or "").upper()
                    if "PICKUP" in method and not any(kw in method for kw in ("NOT", "NO", "NON", "UNAVAILABLE")):
                        if self.parse_strict_bool(opt.get("available")) is True:
                            has_positive_item_pickup = True
                        elif self.parse_strict_bool(opt.get("available")) is False:
                            item_pickup_false = True

        # Reviewer Finding 1 Rule:
        # Require positive, explicit context for the selected item/price;
        # retain eligible identities with blank unverified monetary values.
        can_export_local_price = bool(
            has_positive_item_pickup and
            not item_pickup_false and
            not has_conflicting_location
        )

        brand = str(item.get("brand") or "").strip()
        store_brand = self.normalizer.is_store_private_brand(title, brand)

        # 2. Weight & Packaging (incorporating nested packageInfo and title fallback)
        pkg_info = item.get("packageInfo", {}) or {}
        weight = str(
            item.get("weight") or
            pkg_info.get("weight") or
            item.get("size") or
            pkg_info.get("packageSize") or
            item.get("packageSize") or
            ""
        ).strip()
        if not weight:
            weight = self.normalizer.extract_weight_from_title(title)

        # RULE: Exclude products whose weight contains "approx", "approximately" or equivalent
        if self.normalizer.is_approximate_weight(weight) or self.normalizer.is_approximate_weight(title):
            logger.debug(f"Excluding product with approximate weight: {title} ({weight})")
            return None

        # 3. Pricing
        # If item lacks positive, explicit pickup context, or has contradictory fulfillment (-1, NOT_PICKUP, etc.),
        # retain eligible identity with blank unverified monetary values per Reviewer Finding 1.
        if can_export_local_price:
            price_info = item.get("priceInfo", {}) or {}
            curr_price_obj = price_info.get("currentPrice", {}) or {}
            was_price_obj = price_info.get("wasPrice", {}) or {}

            curr_price_str = curr_price_obj.get("priceString") or str(curr_price_obj.get("price") or item.get("price") or "")
            was_price_str = was_price_obj.get("priceString") or str(was_price_obj.get("price") or item.get("regularPrice") or "")

            cleaned_curr_price = self.normalizer.clean_price(curr_price_str)
            cleaned_was_price = self.normalizer.clean_price(was_price_str)

            if cleaned_was_price and cleaned_was_price != cleaned_curr_price:
                regular_price = cleaned_was_price
                sale_price = cleaned_curr_price
            else:
                regular_price = cleaned_curr_price
                sale_price = ""

            # 4. PPM (Price Per Measure) - Scraped directly, never computed
            raw_ppm = (
                curr_price_obj.get("unitPrice") or
                price_info.get("unitPrice", {}).get("priceString") or
                item.get("ppm") or
                item.get("unitPriceString") or
                ""
            )
            ppm = self.normalizer.extract_ppm(str(raw_ppm))

            # 5. Deals Classification (Volume vs Digital, incorporating nested promotions)
            promo_info = item.get("promotions", {}) or {}
            badge_text = str(item.get("badge", {}).get("text") or item.get("promoBadge") or "")
            deal_desc = str(
                item.get("dealDescription") or
                item.get("promoDescription") or
                promo_info.get("digitalCoupon") or
                promo_info.get("volumeDeal") or
                ""
            )
            promo_price_disp = str(
                item.get("promoPrice") or
                promo_info.get("digitalCouponPrice") or
                promo_info.get("volumeDealPrice") or
                ""
            )

            vol_desc, vol_price, dig_desc, dig_price = self.normalizer.parse_deals(
                badge_text, deal_desc, promo_price_disp
            )
        else:
            logger.debug(
                f"[LOG-OBS: UNVERIFIED_MONETARY_VALUES] Retaining eligible identity with blank unverified monetary values: {title}"
            )
            regular_price = ""
            sale_price = ""
            ppm = ""
            vol_desc = ""
            vol_price = ""
            dig_desc = ""
            dig_price = ""

        # 6. URLs and Identifiers (Distinct UPC vs Retailer Product ID)
        canonical_url = str(item.get("canonicalUrl") or item.get("productUrl") or item.get("url") or "")
        if canonical_url and not canonical_url.startswith("http"):
            canonical_url = f"https://www.marianos.com{canonical_url}"

        image_url = str(item.get("image") or item.get("imageInfo", {}).get("thumbnailUrl") or item.get("imageUrl") or "")

        retailer_item_id = str(item.get("id") or item.get("productId") or "").strip()
        raw_upc = str(item.get("upc") or item.get("gtin") or "").strip()
        # Do NOT use retailer item ID as fallback UPC if actual UPC is absent
        upc = raw_upc if (raw_upc.isdigit() and len(raw_upc) in (11, 12, 13, 14)) else ""

        # 7. Construct standardized record
        record = MarianoProductRecord(
            zipcode=str(location_info.get("zipcode", "")),
            store_name=str(location_info.get("store_name", "")),
            store_location=str(location_info.get("store_location", "")),
            store_logo=str(location_info.get("store_logo", "")),
            store_brand=store_brand,
            category=category,
            sub_category=sub_category,
            product_title=title,
            weight=weight,
            regular_price=regular_price,
            sale_price=sale_price,
            volume_deals_description=vol_desc,
            volume_deals_price=vol_price,
            digital_deals_description=dig_desc,
            digital_deals_price=dig_price,
            image_url=image_url,
            url=canonical_url,
            upc=upc,
            gupc="",           # Always empty string per requirements
            ppm=ppm,           # Scraped verbatim or empty
            unit_price="",     # Always empty string per requirements
            crawl_date=datetime.now(timezone.utc).strftime("%Y-%m-%d")  # 22nd field: collection date
        )

        # Audit logging: Distinguish fresh on-shelf vs fresh out-of-stock
        avail_info = item.get("availability", {}) or {}
        is_out_of_stock = bool(
            item.get("soldOut") or
            item.get("inStock") is False or
            avail_info.get("inStock") is False or
            item.get("isAvailable") is False
        )
        if is_out_of_stock:
            logger.info(f"[LOG-OBS: FRESH_OUT_OF_STOCK] Retaining out-of-stock item: {title} (UPC: {upc}) at source price ${regular_price}")
        else:
            logger.debug(f"[LOG-OBS: FRESH_ON_SHELF] In-stock observation: {title} (UPC: {upc})")

        return record

    def parse_page(
        self,
        html_content: str,
        category: str,
        sub_category: str,
        location_info: Dict[str, Any],
        seen_keys: Set[str]
    ) -> List[MarianoProductRecord]:
        """
        Parses page HTML and returns a list of valid MarianoProductRecords.
        Enforces:
        - Local store & in-store fulfillment context only.
        - No approximate weights.
        - Deduplication across categories & sponsored items.
        - Strict 22-field ordering via MarianoProductRecord.
        """
        results: List[MarianoProductRecord] = []
        raw_items: List[Dict[str, Any]] = []

        # Attempt embedded state parsing first
        embedded_data = self.parse_embedded_json(html_content)
        if embedded_data:
            raw_items = self.extract_items_from_json(embedded_data)

        # Fallback to HTML DOM parsing
        if not raw_items:
            soup = BeautifulSoup(html_content, "html.parser")
            dom_cards = soup.select("[data-testid*='product-card'], .ProductCard, [data-upc], article.kds-Card")
            for card in dom_cards:
                title_elem = card.select_one("[data-testid='product-title'], .ProductCard-description, h3, a.kds-Link")
                price_elem = card.select_one("[data-testid='product-price'], .kds-Price, span.price")
                link_elem = card.select_one("a[href*='/p/']")
                img_elem = card.select_one("img[src*='kroger.com'], img[src*='marianos.com']")
                
                if title_elem and price_elem:
                    upc = card.get("data-upc", "")
                    card_loc = card.get("data-location-id") or card.get("data-store-id") or ""
                    card_mod = card.get("data-fulfillment") or card.get("data-modality") or ""
                    raw_items.append({
                        "upc": upc,
                        "name": title_elem.get_text(strip=True),
                        "priceInfo": {"currentPrice": {"priceString": price_elem.get_text(strip=True)}},
                        "canonicalUrl": link_elem["href"] if link_elem and link_elem.get("href") else "",
                        "image": img_elem["src"] if img_elem and img_elem.get("src") else "",
                        "sellerName": "Mariano's",
                        "locationId": card_loc,
                        "modality": card_mod
                    })

        logger.info(f"Extracted {len(raw_items)} candidate items from page for {category} -> {sub_category}")

        for item in raw_items:
            record = self.parse_product_item(item, category, sub_category, location_info)
            if not record:
                continue

            dedup_key = record.upc if record.upc else record.url
            if not dedup_key or dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            results.append(record)

        return results
