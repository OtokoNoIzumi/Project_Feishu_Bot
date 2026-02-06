"""
Search Services.

Centralizes search logic for Food (Dish/Product) and Global content (Dialogues/Cards).
Refactored to use atomic services: ProductSearchService, DishSearchService, etc.
"""

from collections import defaultdict
from typing import Any, Dict, List
from apps.diet.data_source import ProductSource, DishSource
from apps.common.dialogue_service import DialogueService
from libs.utils.energy_units import macro_energy_kj
from libs.utils.text_utils.pinyin_util import extract_phonetics


class Matcher:
    """Core text matching utility."""

    @staticmethod
    def match(text: str, query: str) -> bool:
        """
        Match if all space-separated parts of query exist in text.
        e.g. "foo bar" matches "bar baz foo"
        Case insensitive.
        """
        if not query:
            return True
        if not text:
            return False

        text_lower = text.lower()
        parts = query.lower().split()

        # All parts must be present (AND logic)
        for part in parts:
            if part not in text_lower:
                return False
        return True


# region 产品搜索
class ProductSearchService:
    """Product Search Service."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search products with deduplication (Brand + Name + Variant).
        Returns unique products matching query.
        """
        raw_list = ProductSource.fetch_recent(self.user_id, limit=2000)

        # Deduplication Strategy
        seen_keys = set()
        results = []

        for p in reversed(raw_list):
            # Construct deduplication key
            p_name = p.get("product_name", "") or p.get("name", "")
            brand = p.get("brand", "")
            variant = p.get("variant", "")
            key = (brand, p_name, variant)

            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Match Logic
            # Combine fields for matching: "Brand Name Variant"
            full_text = f"{brand} {p_name} {variant}"
            
            # Check Text Match OR Pinyin Match
            is_match = Matcher.match(full_text, query)
            if not is_match:
                # Try pinyin matching
                pinyin_initials = p.get("pinyin_initials", [])
                for pi in pinyin_initials:
                    if Matcher.match(pi, query):
                        is_match = True
                        break
            
            if is_match:
                results.append(p)
                if len(results) >= limit:
                    break

        return results

    def get_recommendations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get latest unique products (Empty Query).
        """
        # Reuse search logic with empty query -> returns unique latest items
        return self.search(query="", limit=limit)


# endregion


# region 菜式搜索
class DishSearchService:
    """Dish Search Service."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def search_aggregated(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search dishes and return AGGREGATED results (grouped by name).
        """
        # Fetch more to allow for aggregation compression
        raw_list = DishSource.fetch_recent(self.user_id, limit=1000)

        # Grouping
        grouped = defaultdict(list)
        for d in raw_list:
            name = d.get("dish_name", "")
            if not name:
                continue
            # Filter first (efficiency optimization for typed search)
            # If query exists, only group items that match.
            if query:
                # Text Match
                is_match = Matcher.match(name, query)
                if not is_match:
                     # Pinyin Match
                     pinyin_initials = d.get("pinyin_initials", [])
                     for pi in pinyin_initials:
                         if Matcher.match(pi, query):
                             is_match = True
                             break
                if not is_match:
                    continue
            grouped[name].append(d)

        # Aggregation
        results = []
        for name, group in grouped.items():
            if not group:
                continue

            # Basic info from most recent entry
            latest = group[0]

            # Calculate average nutrition from group
            total_w = 0
            total_p = 0
            total_f = 0
            total_c = 0
            total_fib = 0
            total_na = 0
            valid_count = 0

            for item in group:
                total_w += item.get("recorded_weight_g", 0)
                macros = item.get("macros_per_100g", {})
                if macros:
                    total_p += float(macros.get("protein_g", 0) or 0)
                    total_f += float(macros.get("fat_g", 0) or 0)
                    total_c += float(macros.get("carbs_g", 0) or 0)
                    total_fib += float(macros.get("fiber_g", 0) or 0)
                    total_na += float(macros.get("sodium_mg", 0) or 0)
                    valid_count += 1

            if valid_count > 0:
                p = total_p / valid_count
                f = total_f / valid_count
                c = total_c / valid_count
                fib = total_fib / valid_count
                na = total_na / valid_count
                w = round(total_w / valid_count, 1)

                # Recalculate Energy Density (kJ/100g)
                # This ensures consistency as energy is derived from macros
                e = macro_energy_kj(p, f, c)

                avg_macros = {
                    "energy_kj": round(e, 2),
                    "protein_g": round(p, 1),
                    "fat_g": round(f, 1),
                    "carbs_g": round(c, 1),
                    "fiber_g": round(fib, 1),
                    "sodium_mg": round(na, 0),
                }
            else:
                avg_macros = latest.get("macros_per_100g", {})
                w = latest.get("recorded_weight_g", 100)

            # Construct result object
            result_item = {
                "dish_name": name,
                "recorded_weight_g": w,
                "macros_per_100g": avg_macros,
                "count": len(group),  # Meta info: how many times eaten
                "last_eaten": latest.get("created_at"),
            }
            results.append(result_item)

        results.sort(key=lambda x: x["last_eaten"], reverse=True)

        return results[:limit]

    def get_recommendations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get latest unique dishes (Empty Query)."""
        return self.search_aggregated(query="", limit=limit)


# endregion


# region 餐食记录搜索
class CardSearchService:
    """Card Search Service."""

    def __init__(self, service: DialogueService):
        self.service = service

    def search_history(
        self, query: str, limit: int = 20, saved_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search cards in memory index.
        """
        # Logic adapted from DialogueService but using Matcher
        candidates = []

        # Reversed: Recent first
        for card in reversed(self.service.card_index):
            if saved_only and card.get("status") != "saved":
                continue

            # Match Query
            # Match against: User Title, Meal Name, Dish Names
            title = card.get("user_title", "")
            meal_name = card.get("meal_name", "")
            dish_names = " ".join(card.get("dish_names", []) or [])

            full_text = f"{title} {meal_name} {dish_names}"

            if Matcher.match(full_text, query):
                candidates.append(card)
            else:
                 # Pinyin Match (Lazy Cache)
                 if "_pinyin_initials" not in card:
                      # Generate pinyin for the search text
                      # We use the same full_text or regenerate from specific fields?
                      # Using full_text is accurate enough.
                      phonetics = extract_phonetics(full_text)
                      card["_pinyin_initials"] = phonetics.get("pinyin_initials", [])
                 
                 for pi in card["_pinyin_initials"]:
                      if Matcher.match(pi, query):
                           candidates.append(card)
                           break

            if len(candidates) >= limit:
                break

        return candidates


# endregion


# region 对话搜索
class DialogueSearchService:
    """Dialogue Search Service."""

    def __init__(self, service: DialogueService):
        self.service = service

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search dialogues by title."""
        candidates = []
        for d in reversed(self.service.dialogue_index):
            title = d.get("title", "")
            if Matcher.match(title, query):
                candidates.append(d)
                if len(candidates) >= limit:
                    break
        return candidates


# endregion
