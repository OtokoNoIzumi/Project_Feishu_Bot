"""
Diet Memory Service.

Retrieves and formats recent product memories to assist LLM in recognizing
habitual food items.
"""

from typing import List
from apps.common.record_service import global_storage


def get_product_memories(user_id: str, limit: int = 50) -> List[str]:
    """
    Get user's recent product label memories (from product_library.jsonl).
    Used to help LLM recognize similar products.

    Logic:
    - Read reversed (Newest first).
    - Deduplicate by 'product_name'.
    - Return formatted strings.
    """
    # pylint: disable=too-many-locals
    records = global_storage.read_dataset(
        user_id, "diet", "product_library.jsonl", limit=limit
    )

    seen_names = set()
    memories = []

    for rec in records:
        name = rec.get("product_name", "").strip()
        if not name:
            continue

        key = name
        if key in seen_names:
            continue
        seen_names.add(key)

        brand = rec.get("brand", "").strip()
        variant = rec.get("variant", "").strip()

        # Schema Note: Use post-processed fields (_per_serving)
        p = rec.get("protein_g_per_serving", 0)
        f = rec.get("fat_g_per_serving", 0)
        c = rec.get("carbs_g_per_serving", 0)
        na = rec.get("sodium_mg_per_serving", 0)
        fib = rec.get("fiber_g_per_serving", 0)
        energy_kj = rec.get("energy_kj_per_serving", 0)

        # Format: [Brand Name] (Variant) E=... P=...
        info = f"- [{brand} {name}]"
        if variant:
            info += f" ({variant})"

        t_amt = rec.get("table_amount", 100)
        t_unit = rec.get("table_unit", "g")
        serving = f"{t_amt}{t_unit}"
        info += f" Energy:{energy_kj}KJ/{serving}"

        if any([p, f, c, na, fib]):
            info += f" | P:{p}g F:{f}g C:{c}g Na:{na}mg Fib:{fib}g"

        note = rec.get("custom_note", "").strip()
        if note:
            info += f" | Note:{note}"

        memories.append(info)

        if len(memories) >= 20:
            break

    return memories
