"""
Diet 后处理层

Why this exists?
虽然 LLM Schema 已经定义了结构，但实际工程中需要做必要的清洗和计算，例如：
1. 能量单位统一：Ocr 可能是 Kcal，这里统一转 KJ。
2. 总量聚合计算：LLM 算数不可靠，我们在代码里自己加总 total_energy / net_weight。
3. 字段清洗：确保 None 变成 0.0 或空字符串，防止下游报错。
"""

from typing import Any, Dict, List

from libs.utils.energy_units import kcal_to_kj, macro_energy_kj


def normalize_captured_labels(llm_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize captured labels (energy units, defaults)."""
    labels: List[Dict[str, Any]] = []
    for raw in llm_result.get("captured_labels") or []:
        if not isinstance(raw, dict):
            continue
        unit = (raw.get("energy_unit") or "KJ").strip()
        value = float(raw.get("energy_value") or 0.0)
        energy_kj = kcal_to_kj(value) if unit == "Kcal" else value
        labels.append(
            {
                "product_name": str(raw.get("product_name") or ""),
                "brand": str(raw.get("brand") or ""),
                "variant": str(raw.get("variant") or ""),
                "serving_size": str(raw.get("serving_size") or "100g"),
                "energy_kj_per_serving": energy_kj,
                "protein_g_per_serving": float(raw.get("protein_g") or 0.0),
                "fat_g_per_serving": float(raw.get("fat_g") or 0.0),
                "carbs_g_per_serving": float(raw.get("carbs_g") or 0.0),
                "sodium_mg_per_serving": float(raw.get("sodium_mg") or 0.0),
                "fiber_g_per_serving": float(raw.get("fiber_g") or 0.0),
                "custom_note": str(raw.get("custom_note") or ""),
            }
        )
    return labels



def _match_label_for_ingredient(
    labels: List[Dict[str, Any]], ingredient_name: str
) -> Dict[str, Any] | None:
    """Find a matching label for the given ingredient name."""
    name = (ingredient_name or "").strip()
    if not name:
        return None
    for lb in labels:
        pn = lb.get("product_name", "")
        if pn and (pn in name or name in pn):
            return lb
    return None


def finalize_record(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finalize the diet record by normalizing data and calculating totals.

    Aggregates dish macros, applies labels to ingredients, and cleans up fields.
    """
    # pylint: disable=too-many-locals
    labels = normalize_captured_labels(llm_result)

    total_energy_kj = 0.0
    total_weight_g = 0.0

    dishes_out: List[Dict[str, Any]] = []
    for dish in llm_result.get("dishes") or []:
        if not isinstance(dish, dict):
            continue
        ing_out: List[Dict[str, Any]] = []
        for ing in dish.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            name_zh = str(ing.get("name_zh") or "")
            weight_g = float(ing.get("weight_g") or 0.0)
            macros = ing.get("macros") or {}
            protein_g = float((macros.get("protein_g") or 0.0))
            fat_g = float((macros.get("fat_g") or 0.0))
            carbs_g = float((macros.get("carbs_g") or 0.0))
            sodium_mg = float((macros.get("sodium_mg") or 0.0))
            fiber_g = float((macros.get("fiber_g") or 0.0))

            data_source = str(ing.get("data_source") or "generic_estimate")
            energy_kj = macro_energy_kj(protein_g, fat_g, carbs_g)

            if data_source == "label_ocr":
                lb = _match_label_for_ingredient(labels, name_zh)
                if lb:
                    serving = lb.get("serving_size") or "100g"
                    per = float(lb.get("energy_kj_per_serving") or 0.0)
                    if serving in ("100g", "100ml") and weight_g > 0:
                        energy_kj = (per / 100.0) * weight_g
                    elif serving == "per_pack":
                        energy_kj = macro_energy_kj(protein_g, fat_g, carbs_g)

            energy_kj = float(energy_kj)
            total_energy_kj += energy_kj
            total_weight_g += weight_g

            ing_out.append(
                {
                    "name_zh": name_zh,
                    "weight_g": round(weight_g, 4),
                    "weight_method": str(
                        ing.get("weight_method") or "pure_visual_estimate"
                    ),
                    "data_source": data_source,
                    "energy_kj": round(energy_kj, 4),
                    "macros": {
                        "protein_g": round(protein_g, 4),
                        "fat_g": round(fat_g, 4),
                        "carbs_g": round(carbs_g, 4),
                        "sodium_mg": round(sodium_mg, 4),
                        "fiber_g": round(fiber_g, 4),
                    },
                }
            )

        dishes_out.append(
            {
                "standard_name": str(dish.get("standard_name") or ""),
                "ingredients": ing_out,
            }
        )

    meal_summary_in = llm_result.get("meal_summary") or {}
    advice = str(meal_summary_in.get("advice") or "")
    diet_time = str(meal_summary_in.get("diet_time") or "snack")
    
    # 生成 meal_name：采用"餐时 菜名等N个"格式
    # 这个默认值会用于搜索匹配和显示
    meal_time_map = {
        "snack": "加餐",
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
    }
    meal_time_label = meal_time_map.get(diet_time, "饮食")
    
    if dishes_out:
        first_dish_name = dishes_out[0].get("standard_name") or "未命名"
        if len(dishes_out) == 1:
            meal_name = f"{meal_time_label} {first_dish_name}"
        else:
            meal_name = f"{meal_time_label} {first_dish_name}等{len(dishes_out)}个"
    else:
        meal_name = meal_time_label

    result = {
        "meal_summary": {
            "meal_name": meal_name,
            "total_energy_kj": round(total_energy_kj, 4),
            "net_weight_g": round(total_weight_g, 4),
            "advice": advice,
            "diet_time": diet_time,
        },
        "captured_labels": labels,
        "dishes": dishes_out,
        "user_note_process": str(llm_result.get("user_note_process") or ""),
    }

    # 保留 extra_image_summary（如果 LLM 输出了）
    extra_image_summary = llm_result.get("extra_image_summary")
    if extra_image_summary and str(extra_image_summary).strip():
        result["extra_image_summary"] = str(extra_image_summary).strip()

    # 保留 occurred_at (补录时间)
    occurred_at = llm_result.get("occurred_at")
    if occurred_at and str(occurred_at).strip():
        result["occurred_at"] = str(occurred_at).strip()

    return result
