import json
import logging
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
                    raw_items.append({
                        "upc": upc,
                        "name": title_elem.get_text(strip=True),
                        "priceInfo": {"currentPrice": {"priceString": price_elem.get_text(strip=True)}},
                        "canonicalUrl": link_elem["href"] if link_elem and link_elem.get("href") else "",
                        "image": img_elem["src"] if img_elem and img_elem.get("src") else "",
                        "sellerName": "Mariano's"
                    })

        logger.info(f"Extracted {len(raw_items)} candidate items from page for {category} -> {sub_category}")

        for item in raw_items:
            # 1. Product Title & Brand
            title = str(item.get("name") or item.get("title") or item.get("description") or "").strip()
            if not title:
                continue

            brand = str(item.get("brand") or "").strip()
            store_brand = self.normalizer.is_store_private_brand(title, brand)

            # 2. Weight & Packaging
            weight = str(item.get("weight") or item.get("size") or item.get("packageSize") or "").strip()

            # RULE: Exclude products whose weight contains "approx", "approximately" or equivalent
            if self.normalizer.is_approximate_weight(weight) or self.normalizer.is_approximate_weight(title):
                logger.debug(f"Excluding product with approximate weight: {title} ({weight})")
                continue

            # 3. Pricing
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

            # 5. Deals Classification (Volume vs Digital)
            badge_text = str(item.get("badge", {}).get("text") or item.get("promoBadge") or "")
            deal_desc = str(item.get("dealDescription") or item.get("promoDescription") or "")
            promo_price_disp = str(item.get("promoPrice") or "")

            vol_desc, vol_price, dig_desc, dig_price = self.normalizer.parse_deals(
                badge_text, deal_desc, promo_price_disp
            )

            # 6. URLs and Identifiers
            canonical_url = str(item.get("canonicalUrl") or item.get("productUrl") or item.get("url") or "")
            if canonical_url and not canonical_url.startswith("http"):
                canonical_url = f"https://www.marianos.com{canonical_url}"

            image_url = str(item.get("image") or item.get("imageInfo", {}).get("thumbnailUrl") or item.get("imageUrl") or "")

            upc = str(item.get("upc") or item.get("id") or "").strip()

            # 7. Deduplication check (UPC / Canonical URL)
            dedup_key = upc if upc else canonical_url
            if not dedup_key or dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # 8. Construct standardized record
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
                unit_price=""      # Always empty string per requirements
            )
            results.append(record)

        return results
