from typing import Dict, Any, Optional

class ItamAssetService:
    def __init__(self, db):
        self.db = db

    def calculate_depreciation(
        self,
        purchase_price: float,
        salvage_value: float,
        useful_life_years: int,
        years_elapsed: int
    ) -> float:
        """Straight-line depreciation calculation."""
        if useful_life_years <= 0:
            return purchase_price

        annual_depreciation = (purchase_price - salvage_value) / useful_life_years
        book_value = purchase_price - (annual_depreciation * years_elapsed)
        return max(book_value, salvage_value)

    async def get_asset_depreciation_details(self, asset_id: str, tenant_id: str) -> Dict[str, Any]:
        asset = await self.db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
        if not asset:
            return {}

        purchase_price = asset.get("purchaseCostCents", 0) / 100 # Assuming cents to dollars conversion if needed
        salvage_value = asset.get("salvage_value", 0.0)
        useful_life_years = asset.get("useful_life_years", 0)

        if useful_life_years == 0 or purchase_price == 0:
            return {"book_value": purchase_price, "message": "Depreciation info incomplete"}

        # Simple elapsed years calculation based on purchase date
        purchase_date_str = asset.get("purchaseDate")
        if not purchase_date_str:
            return {"book_value": purchase_price, "message": "Purchase date missing"}

        # Simplified year difference
        from datetime import datetime
        try:
            purchase_date = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
            now = datetime.now(datetime.now().astimezone().tzinfo)
            years_elapsed = (now - purchase_date).days // 365
        except:
            return {"book_value": purchase_price, "message": "Invalid purchase date"}

        book_value = self.calculate_depreciation(purchase_price, salvage_value, useful_life_years, years_elapsed)

        return {
            "book_value": book_value,
            "annual_depreciation": (purchase_price - salvage_value) / useful_life_years,
            "years_elapsed": years_elapsed
        }
