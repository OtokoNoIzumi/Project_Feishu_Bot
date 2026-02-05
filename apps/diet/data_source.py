"""
Data Source for Diet.
"""
from typing import List, Dict, Any
from libs.storage_lib import global_storage


class ProductSource:
    """raw data access for product_library.jsonl"""

    @staticmethod
    def fetch_recent(user_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        """Fetch raw products, latest first."""
        return global_storage.read_dataset(
            user_id=user_id,
            category="diet",
            filename="product_library.jsonl",
            limit=limit,
        )


class DishSource:
    """raw data access for dish_library.jsonl"""

    @staticmethod
    def fetch_recent(user_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch raw dishes, latest first."""
        return global_storage.read_dataset(
            user_id=user_id, category="diet", filename="dish_library.jsonl", limit=limit
        )
