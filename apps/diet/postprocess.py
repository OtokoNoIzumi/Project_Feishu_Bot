"""
Diet 后处理层

Why this exists?
虽然 LLM Schema 已经定义了结构，但实际工程中需要做必要的清洗和计算，例如：
1. 能量单位统一：Ocr 可能是 Kcal，这里统一转 KJ。
2. 总量聚合计算：LLM 算数不可靠，我们在代码里自己加总 total_energy / net_weight。
3. 字段清洗：确保 None 变成 0.0 或空字符串，防止下游报错。
"""


from typing import Any, Dict, List, Optional

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
        custom_note = str(raw.get("custom_note") or "")
        density_factor = raw.get("density_factor")
        try:
            density_factor = float(density_factor) if density_factor and density_factor > 0 else 1.0
        except (ValueError, TypeError):
            density_factor = 1.0
        labels.append(
            {
                "product_name": str(raw.get("product_name") or ""),
                "brand": str(raw.get("brand") or ""),
                "variant": str(raw.get("variant") or ""),
                "unit_weight_g": float(raw.get("unit_weight_g") or 0.0),
                "table_unit": str(raw.get("table_unit") or "g"),
                "table_amount": float(raw.get("table_amount") or 100.0),
                
                "density_factor": density_factor,
                "energy_kj_per_serving": energy_kj,
                "protein_g_per_serving": float(raw.get("protein_g") or 0.0),
                "fat_g_per_serving": float(raw.get("fat_g") or 0.0),
                "carbs_g_per_serving": float(raw.get("carbs_g") or 0.0),
                "sodium_mg_per_serving": float(raw.get("sodium_mg") or 0.0),
                "fiber_g_per_serving": float(raw.get("fiber_g") or 0.0),
                "custom_note": custom_note,
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
                    # 1. 确定基准重量 (Ref Weight)
                    # strict reference from label (e.g. 100g -> 100)
                    ref_amount = float(lb.get("table_amount") or 100.0)
                    # density: 100ml -> 103g or 1 scoop -> 25g
                    density = float(lb.get("density_factor") or 1.0)
                    ref_weight_g = ref_amount * density

                    # 2. 计算换算比例 (Ratio)
                    # weight_g 是用户实际摄入量 / 菜品重量
                    ratio = 0.0
                    if ref_weight_g > 0:
                        ratio = weight_g / ref_weight_g

                    # 3. 覆盖 Macros (P/F/C etc)
                    # 按照比例从未经加工的 Label 原文中缩放
                    protein_g = float(lb.get("protein_g_per_serving") or 0.0) * ratio
                    fat_g = float(lb.get("fat_g_per_serving") or 0.0) * ratio
                    carbs_g = float(lb.get("carbs_g_per_serving") or 0.0) * ratio
                    sodium_mg = float(lb.get("sodium_mg_per_serving") or 0.0) * ratio
                    fiber_g = float(lb.get("fiber_g_per_serving") or 0.0) * ratio

                    # 4. 重新计算能量 (Energy) from correct macros
                    # 强一致性：Energy 必须由 P/F/C 算出，忽略 Label OCR 的 Energy 字段
                    # (Label Energy 仅用于 Schema 提取和可能的校验，不直接参与最终计算)
                    energy_kj = macro_energy_kj(protein_g, fat_g, carbs_g)

            # Fallback / Generic: energy_kj is already calculated at start of loop if not label_ocr
            # But if label_ocr, we just overwrote it above.
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
