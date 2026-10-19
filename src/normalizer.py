import re
from typing import Tuple, List, Optional

class DataNormalizer:
    """Handles field sanitization, price normalization, weight validation, and deals parsing for Mariano's."""

    def __init__(self, private_brands: Optional[List[str]] = None):
        self.private_brands = [b.lower() for b in (private_brands or [
            "mariano's", "roundy's", "simple truth", "simple truth organic",
            "private selection", "kroger", "heritage farm", "hemisfares",
            "comforts", "bloom haus", "dip", "big k", "home sense", "pet pride"
        ])]

        # Regex pattern for approximate weight detection
        self.approx_weight_pattern = re.compile(
            r'\b(?:approx|approximately|approx\.|estimated|est\.)\b',
            re.IGNORECASE
        )

        # Regex patterns for price matching
        self.price_pattern = re.compile(r'(\d+(?:\.\d{1,2})?)')

        # Regex for volume deals (no clipping required)
        self.volume_deal_pattern = re.compile(
            r'(?:\d+\s+for\s+\$?\d+(?:\.\d{2})?|'
            r'buy\s+\d+,\s*get\s+\d+\s+free|'
            r'buy\s+\d+\s+get\s+\d+\s+free|'
            r'bogo|'
            r'mix\s+(?:or|and)\s+match\s+\d+\s+for\s+\$?\d+(?:\.\d{2})?|'
            r'save\s+\$?\d+(?:\.\d{2})?\s+when\s+you\s+buy\s+\d+|'
            r'must\s+buy\s+\d+)',
            re.IGNORECASE
        )

        # Regex for digital deals (clip, coupon, activate required)
        self.digital_deal_pattern = re.compile(
            r'(?:clip\s+(?:and\s+save\s+)?coupon|'
            r'clipped\s+coupon|'
            r'with\s+digital\s+coupon|'
            r'digital\s+coupon|'
            r'activate\s+coupon|'
            r'save\s+\$?\d+(?:\.\d{2})?\s+with\s+(?:digital\s+)?coupon)',
            re.IGNORECASE
        )

        # Exclusions for cashback / reward points
        self.cashback_pattern = re.compile(
            r'(?:kroger\s+cash|walmart\s+cash|cashback|cash\s+back|manufacturer\s+offer)',
            re.IGNORECASE
        )

    def is_approximate_weight(self, weight_str: str) -> bool:
        """
        Returns True if the weight contains 'approx', 'approximately', or equivalent.
        Products with approximate weights MUST be excluded per data rules.
        """
        if not weight_str:
            return False
        return bool(self.approx_weight_pattern.search(weight_str))

    def clean_price(self, price_raw: str) -> str:
        """
        Formats prices to consistent numeric format, e.g. '12.98'.
        Returns empty string if invalid or absent.
        """
        if not price_raw:
            return ""
        
        # Remove commas, clean text
        cleaned = str(price_raw).replace(",", "").strip()
        match = self.price_pattern.search(cleaned)
        if match:
            val = float(match.group(1))
            return f"{val:.2f}"
        return ""

    def is_store_private_brand(self, title: str, brand: str) -> str:
        """
        Returns 'yes' if identified as a Kroger/Mariano's private-label product, else 'no'.
        """
        brand_clean = (brand or "").lower().strip()
        title_clean = (title or "").lower().strip()

        for pb in self.private_brands:
            if pb == brand_clean:
                return "yes"
            if re.search(rf'\b{re.escape(pb)}\b', title_clean):
                return "yes"

        return "no"

    # Alias for backward compatibility
    is_walmart_private_brand = is_store_private_brand

    def extract_ppm(self, raw_ppm: str) -> str:
        """
        Extracts displayed Price Per Measure (PPM) directly without modifying or calculating.
        Example: '$0.25/oz', '$3.99/lb', '$0.50/ct'. Returns empty string if not displayed.
        """
        if not raw_ppm:
            return ""
        ppm_str = str(raw_ppm).strip()
        if re.search(r'\$?\d+(?:\.\d{1,2})?\s*/\s*[a-zA-Z]+', ppm_str):
            return ppm_str
        return ppm_str

    def parse_deals(
        self,
        promo_badge: str,
        deal_description: str,
        displayed_promo_price: str
    ) -> Tuple[str, str, str, str]:
        """
        Classifies promotions into Volume Deals vs Digital Deals.
        Returns:
            (volume_deals_description, volume_deals_price, digital_deals_description, digital_deals_price)
        """
        combined_text = f"{promo_badge} {deal_description}".strip()
        if not combined_text:
            return ("", "", "", "")

        # Check for Cashback first - MUST NOT be treated as immediate digital price reductions
        if self.cashback_pattern.search(combined_text) and not self.digital_deal_pattern.search(combined_text):
            return ("", "", "", "")

        # Check Digital Deals
        if self.digital_deal_pattern.search(combined_text):
            promo_price = self.clean_price(displayed_promo_price)
            return ("", "", combined_text, promo_price)

        # Check Volume Deals
        if self.volume_deal_pattern.search(combined_text):
            promo_price = self.clean_price(displayed_promo_price)
            return (combined_text, promo_price, "", "")

        # Fallback check: e.g. "2 for $5"
        if "for $" in combined_text.lower() or "bogo" in combined_text.lower():
            promo_price = self.clean_price(displayed_promo_price)
            return (combined_text, promo_price, "", "")

        return ("", "", "", "")
