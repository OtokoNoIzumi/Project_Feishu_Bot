"""
Search API Router.

Centralizes search logic for Food (Dish/Product) and Global content (Dialogues/Cards).
"""
from collections import defaultdict
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends
from apps.deps import get_current_user_id, require_auth
from apps.settings import BackendSettings
from libs.storage_lib import global_storage
from libs.utils.energy_units import macro_energy_kj
from apps.common.dialogue_service import DialogueService


def build_search_router(settings: BackendSettings) -> APIRouter:
    """Build and return the search API router."""
    router = APIRouter()
    auth_dep = require_auth(settings)

    def get_dialogue_service(
        user_id: str = Depends(get_current_user_id),
    ) -> DialogueService:
        return DialogueService(user_id)

    @router.get("/api/search/food", dependencies=[Depends(auth_dep)])
    async def search_food(q: str, user_id: str = Depends(get_current_user_id)):
        """
        Unified search for Add Dish:
        1. Product Library (exact match or partial)
        2. Dish Library (Aggregated averages)
        Returns mixed list with type='product' or 'dish'.
        """
        q = q.lower().strip()
        has_query = len(q) > 0

        results = []

        # 1. Product Library
        products = global_storage.read_dataset(
            user_id, "diet", "product_library.jsonl", limit=2000
        )
        # Assuming Oldest->Newest, we want Latest versions.
        # But Product Library is upserted? No, record_service appends.
        # record_service L166 rewrites the whole file with dedup logic.
        # So product_library is already unique by key.
        for p in products:
            pname = str(p.get("product_name", "")).lower()
            if (not has_query) or (q in pname):
                results.append({"type": "product", "data": p})
                if len(results) >= 5:
                    break

        # 2. Dish Library (On-demand Aggregation)

        dishes = global_storage.read_dataset(
            user_id, "diet", "dish_library.jsonl", limit=1000
        )

        relevant_groups = defaultdict(list)
        for d in dishes:
            dname = str(d.get("dish_name", "")).lower()
            if (not has_query) or (q in dname):
                w = float(d.get("recorded_weight_g") or 0)
                if w > 0:
                    relevant_groups[d["dish_name"]].append(d)

        # Aggregate found groups
        for name, records in relevant_groups.items():
            count = len(records)
            total_w = sum(float(x.get("recorded_weight_g") or 0) for x in records)
            avg_weight = round(total_w / count, 1)

            # Sum densities
            sum_p = sum(
                float((x.get("macros_per_100g") or {}).get("protein_g") or 0)
                for x in records
            )
            sum_f = sum(
                float((x.get("macros_per_100g") or {}).get("fat_g") or 0)
                for x in records
            )
            sum_c = sum(
                float((x.get("macros_per_100g") or {}).get("carbs_g") or 0)
                for x in records
            )
            sum_na = sum(
                float((x.get("macros_per_100g") or {}).get("sodium_mg") or 0)
                for x in records
            )
            sum_fib = sum(
                float((x.get("macros_per_100g") or {}).get("fiber_g") or 0)
                for x in records
            )

            d_p = sum_p / count
            d_f = sum_f / count
            d_c = sum_c / count
            d_na = sum_na / count
            d_fib = sum_fib / count

            # Recalculate Energy Density (kJ/100g)
            d_e = macro_energy_kj(d_p, d_f, d_c)

            # Latest is last in list (Append order)
            latest = records[-1]

            dish_data = {
                "dish_name": name,
                "recorded_weight_g": avg_weight,
                "macros_per_100g": {
                    "energy_kj": round(d_e, 2),
                    "protein_g": round(d_p, 2),
                    "fat_g": round(d_f, 2),
                    "carbs_g": round(d_c, 2),
                    "sodium_mg": round(d_na, 2),
                    "fiber_g": round(d_fib, 2),
                },
                "ingredients_snapshot": latest.get("ingredients_snapshot", []),
                "count": count,
                "source": "history",
            }
            results.append({"type": "dish", "data": dish_data})
            if len(results) >= 20:
                break

        return results

    @router.get("/api/search/global", dependencies=[Depends(auth_dep)])
    async def search_global(
        q: str,
        user_id: str = Depends(get_current_user_id),
        service: DialogueService = Depends(get_dialogue_service),
    ):
        q = q.lower().strip()
        if len(q) < 1:
            return {"products": [], "cards": [], "dialogues": []}

        products = global_storage.read_dataset(
            user_id, "diet", "product_library.jsonl", limit=2000
        )
        product_matches = []
        seen_prod = set()
        for p in products:
            pname = str(p.get("product_name", "")).lower()
            if q in pname:
                key = (p.get("product_name"), p.get("brand"))
                if key not in seen_prod:
                    seen_prod.add(key)
                    product_matches.append(p)
                    if len(product_matches) >= 5:
                        break

        # 2. Cards (Raw History) using Index
        card_matches = []
        # sort by updated_at desc
        sorted_index = sorted(
            service.card_index, key=lambda x: x["updated_at"], reverse=True
        )

        c_count = 0
        for c in sorted_index:
            if c.get("mode") and c.get("mode") != "diet":
                continue
            matched = False
            if c.get("user_title") and q in c["user_title"].lower():
                matched = True
            elif c.get("meal_name") and q in c["meal_name"].lower():
                matched = True
            else:
                for dn in c.get("dish_names", []):
                    if q in dn.lower():
                        matched = True
                        break

            if matched:
                card_matches.append(c)
                c_count += 1
                if c_count >= 10:
                    break

        # 3. Dialogues
        dialogue_matches = []
        sorted_dialogues = sorted(
            service.dialogue_index, key=lambda x: x["updated_at"], reverse=True
        )
        d_count = 0
        for d in sorted_dialogues:
            if d.get("title") and q in d["title"].lower():
                dialogue_matches.append(d)
                d_count += 1
                if d_count >= 10:
                    break

        return {
            "products": product_matches,
            "cards": card_matches,
            "dialogues": dialogue_matches,
        }

    return router
