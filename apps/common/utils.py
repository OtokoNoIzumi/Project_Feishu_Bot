"""
Shared utilities for the application.
"""

import base64
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import UploadFile


def decode_images_b64(images_b64: List[str]) -> List[bytes]:
    """
    Decode a list of Base64 strings to bytes, silently ignoring errors.

    Args:
        images_b64: List of Base64 strings.

    Returns:
        List of decoded bytes for valid strings.
    """
    out: List[bytes] = []
    for s in images_b64 or []:
        if not s:
            continue
        try:
            out.append(base64.b64decode(s))
        except (ValueError, TypeError):
            continue
    return out


def parse_occurred_at(oa_str: str) -> Optional[datetime]:
    """
    Parse occurrences string from LLM result.
    Supports 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD HH:MM'.
    """
    if not oa_str or not isinstance(oa_str, str):
        return None
    try:
        # Handle potential YYYY-MM-DD HH:MM if SS missing
        clean_str = oa_str.replace(" ", "T")
        if len(clean_str) == 16:  # YYYY-MM-DDTHH:MM
            clean_str += ":00"
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return None


async def read_upload_files(images: List[UploadFile]) -> List[bytes]:
    """Read bytes from a list of UploadFiles, silently ignoring errors."""
    images_bytes: List[bytes] = []
    for f in images or []:
        try:
            images_bytes.append(await f.read())
        # pylint: disable=broad-exception-caught
        except Exception:
            continue
    return images_bytes


def format_diet_records_to_table(
    records: List[Dict[str, Any]], 
    as_list: bool = False
) -> Any:
    """
    Format diet records into a compact text table.
    Shared by Weekly Analysis and Daily Advice.
    
    Format: 日期|餐|菜品|重量g|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g
    
    Args:
        as_list: If True, returns List[str] (rows only, no header).
                 If False (default), returns joined str with header (original behavior).
    """
    if not records:
        return [] if as_list else "无饮食记录"

    # 防御性排序：确保严格按时间顺序
    try:
        sorted_records = sorted(records, key=lambda x: x.get("occurred_at", "") or "")
    except Exception:
        sorted_records = records

    rows = []
    
    for rec in sorted_records:
        occurred = (rec.get("occurred_at") or "")[:10]
        # Fallback if occurred_at is missing/none
        if not occurred: 
            occurred = "Unknown"
        
        # Format Date for compact row: shorten to MM-DD or keep YYYY-MM-DD
        # Original logic kept it as is.
            
        meal_summary = rec.get("meal_summary") or {}
        diet_time = meal_summary.get("diet_time", "?")

        # Map meal type to short Chinese
        meal_map = {"breakfast": "早", "lunch": "午", "dinner": "晚", "snack": "加"}
        meal_short = meal_map.get(diet_time, diet_time[:1])

        dishes = rec.get("dishes", [])
        if not dishes:
             continue

        for dish in dishes:
            dish_name = dish.get("standard_name") or dish.get("dish_name") or "未知"

            # Aggregate dish-level totals from ingredients
            # Logic Update: support both 'ingredients' sum and direct 'macros' if pre-calc
            d_weight = float(dish.get("total_weight_g") or 0)
            d_energy = 0.0
            d_p, d_f, d_c, d_na, d_fib = 0.0, 0.0, 0.0, 0.0, 0.0
            
            # 1. Try sum ingredients first (Legacy & Robustness)
            ingredients = dish.get("ingredients") or []
            if ingredients:
                sum_w = 0.0
                for ing in ingredients:
                    sum_w += float(ing.get("weight_g", 0) or 0)
                    d_energy += float(ing.get("energy_kj", 0) or 0)
                    m = ing.get("macros", {})
                    d_p += float(m.get("protein_g", 0) or 0)
                    d_f += float(m.get("fat_g", 0) or 0)
                    d_c += float(m.get("carbs_g", 0) or 0)
                    d_na += float(m.get("sodium_mg", 0) or 0)
                    d_fib += float(m.get("fiber_g", 0) or 0)
                
                # If d_weight was 0, use sum
                if d_weight == 0:
                     d_weight = sum_w
            
            # 2. If no ingredients or zero energy, check dish.macros (Pruned context case)
            if d_energy == 0 and not ingredients:
                dm = dish.get("macros") or {}
                d_energy = float(dm.get("energy_kj") or 0)
                d_p = float(dm.get("protein_g") or 0)
                d_f = float(dm.get("fat_g") or 0)
                d_c = float(dm.get("carbs_g") or 0)
                d_na = float(dm.get("sodium_mg") or 0)
                d_fib = float(dm.get("fiber_g") or 0)

            # Format row
            row = (
                f"{occurred}|{meal_short}|{dish_name}|"
                f"{d_weight:.0f}|{d_energy:.0f}|"
                f"{d_p:.1f}|{d_f:.1f}|{d_c:.1f}|"
                f"{d_na:.0f}|{d_fib:.1f}"
            )
            rows.append(row)

    if as_list:
        return rows

    # Header row for default string output
    lines = ["日期|餐|菜品|重量g|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g"]
    lines.append("-" * 80)
    lines.extend(rows)

    return "\n".join(lines)
