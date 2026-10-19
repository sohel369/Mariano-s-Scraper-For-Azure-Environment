from typing import Dict, Any, Optional
from collections import OrderedDict
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator

class MarianoProductRecord(BaseModel):
    """
    Enforces the exact 22-field JSON structure and field ordering
    required by the Mariano's Scraper technical specification.
    """
    zipcode: str = Field(default="", description="Store Zip Code")
    store_name: str = Field(default="", description="Mariano's Store Name")
    store_location: str = Field(default="", description="Store Street Address, City, State")
    store_logo: str = Field(default="", description="Mariano's Store Logo URL")
    store_brand: str = Field(default="no", description="'yes' for Kroger/Mariano's private-label, else 'no'")
    category: str = Field(default="", description="Category Name")
    sub_category: str = Field(default="", description="Subcategory Name")
    product_title: str = Field(default="", description="Full product title")
    weight: str = Field(default="", description="Product weight or package size")
    regular_price: str = Field(default="", description="Original/Regular numeric price")
    sale_price: str = Field(default="", description="Sale/Promotional numeric price if discounted")
    volume_deals_description: str = Field(default="", description="Volume deal terms, e.g. 2 for $5, BOGO")
    volume_deals_price: str = Field(default="", description="Promotional volume deal price if displayed")
    digital_deals_description: str = Field(default="", description="Digital coupon terms, e.g. Clip Coupon: Save $2")
    digital_deals_price: str = Field(default="", description="Promotional price after digital coupon if displayed")
    image_url: str = Field(default="", description="Original product image URL")
    url: str = Field(default="", description="Original product page URL")
    upc: str = Field(default="", description="Original UPC barcode")
    gupc: str = Field(default="", description="Always empty string; reserved for downstream pipeline")
    ppm: str = Field(default="", description="Price Per Measure as displayed, e.g. $0.25/oz, else empty string")
    unit_price: str = Field(default="", description="Always empty string; reserved for downstream pipeline")
    crawl_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        description="Collection date, always the final field"
    )

    @field_validator("*", mode="before")
    @classmethod
    def convert_none_to_empty_string(cls, v: Any) -> Any:
        """Converts any None or null values to an empty string."""
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        return str(v)

    @field_validator("gupc", "unit_price", mode="after")
    @classmethod
    def enforce_empty_fields(cls, v: str) -> str:
        """Enforces that gupc and unit_price remain empty strings as required."""
        return ""

    @field_validator("store_brand", mode="after")
    @classmethod
    def validate_store_brand(cls, v: str) -> str:
        """Enforces store_brand is strictly 'yes' or 'no'."""
        val = str(v).lower().strip()
        return "yes" if val in ["yes", "true", "1"] else "no"

    @classmethod
    def get_field_order(cls) -> list[str]:
        return list(cls.model_fields.keys())

    def to_ordered_dict(self) -> OrderedDict:
        """
        Returns an OrderedDict guaranteeing the exact 22-field sequence
        prescribed in the contest specification.
        """
        ordered_fields = [
            ("zipcode", self.zipcode),
            ("store_name", self.store_name),
            ("store_location", self.store_location),
            ("store_logo", self.store_logo),
            ("store_brand", self.store_brand),
            ("category", self.category),
            ("sub_category", self.sub_category),
            ("product_title", self.product_title),
            ("weight", self.weight),
            ("regular_price", self.regular_price),
            ("sale_price", self.sale_price),
            ("volume_deals_description", self.volume_deals_description),
            ("volume_deals_price", self.volume_deals_price),
            ("digital_deals_description", self.digital_deals_description),
            ("digital_deals_price", self.digital_deals_price),
            ("image_url", self.image_url),
            ("url", self.url),
            ("upc", self.upc),
            ("gupc", self.gupc),
            ("ppm", self.ppm),
            ("unit_price", self.unit_price),
            ("crawl_date", self.crawl_date)
        ]
        return OrderedDict(ordered_fields)

# Alias for backwards compatibility with any legacy imports
WalmartProductRecord = MarianoProductRecord
