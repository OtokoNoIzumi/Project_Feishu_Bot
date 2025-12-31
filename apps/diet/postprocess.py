from typing import Any, Dict, List


def _kcal_to_kj(kcal: float) -> float:
    return float(kcal) * 4.184


def normalize_captured_labels(llm_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    labels: List[Dict[str, Any]] = []
    for raw in (llm_result.get("captured_labels") or []):
        if not isinstance(raw, dict):
            continue
        unit = (raw.get("energy_unit") or "KJ").strip()
        value = float(raw.get("energy_value") or 0.0)
        energy_kj = _kcal_to_kj(value) if unit == "Kcal" else value
        labels.append(
            {
                "product_name": str(raw.get("product_name") or ""),
                "brand": str(raw.get("brand") or ""),
                "variant": str(raw.get("variant") or ""),
                "serving_size": str(raw.get("serving_size") or "100g"),
                "energy_kj_per_serving": round(energy_kj, 4),
                "protein_g_per_serving": float(raw.get("protein_g") or 0.0),
                "fat_g_per_serving": float(raw.get("fat_g") or 0.0),
                "carbs_g_per_serving": float(raw.get("carbs_g") or 0.0),
                "sodium_mg_per_serving": float(raw.get("sodium_mg") or 0.0),
            }
        )
    return labels


def _macro_energy_kj(protein_g: float, fat_g: float, carbs_g: float) -> float:
    return (protein_g * 4 + carbs_g * 4 + fat_g * 9) * 4.184


def _match_label_for_ingredient(labels: List[Dict[str, Any]], ingredient_name: str) -> Dict[str, Any] | None:
    name = (ingredient_name or "").strip()
    if not name:
        return None
    for lb in labels:
        pn = lb.get("product_name", "")
        if pn and (pn in name or name in pn):
            return lb
    return None


def finalize_record(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    labels = normalize_captured_labels(llm_result)

    total_energy_kj = 0.0
    total_weight_g = 0.0

    dishes_out: List[Dict[str, Any]] = []
    for dish in (llm_result.get("dishes") or []):
        if not isinstance(dish, dict):
            continue
        ing_out: List[Dict[str, Any]] = []
        for ing in (dish.get("ingredients") or []):
            if not isinstance(ing, dict):
                continue
            name_zh = str(ing.get("name_zh") or "")
            weight_g = float(ing.get("weight_g") or 0.0)
            macros = ing.get("macros") or {}
            protein_g = float((macros.get("protein_g") or 0.0))
            fat_g = float((macros.get("fat_g") or 0.0))
            carbs_g = float((macros.get("carbs_g") or 0.0))
            sodium_mg = float((macros.get("sodium_mg") or 0.0))

            data_source = str(ing.get("data_source") or "generic_estimate")
            energy_kj = _macro_energy_kj(protein_g, fat_g, carbs_g)

            if data_source == "label_ocr":
                lb = _match_label_for_ingredient(labels, name_zh)
                if lb:
                    serving = lb.get("serving_size") or "100g"
                    per = float(lb.get("energy_kj_per_serving") or 0.0)
                    if serving in ("100g", "100ml") and weight_g > 0:
                        energy_kj = (per / 100.0) * weight_g
                    elif serving == "per_pack":
                        energy_kj = _macro_energy_kj(protein_g, fat_g, carbs_g)

            energy_kj = float(energy_kj)
            total_energy_kj += energy_kj
            total_weight_g += weight_g

            ing_out.append(
                {
                    "name_zh": name_zh,
                    "weight_g": round(weight_g, 4),
                    "weight_method": str(ing.get("weight_method") or "pure_visual_estimate"),
                    "data_source": data_source,
                    "energy_kj": round(energy_kj, 4),
                    "macros": {
                        "protein_g": round(protein_g, 4),
                        "fat_g": round(fat_g, 4),
                        "carbs_g": round(carbs_g, 4),
                        "sodium_mg": round(sodium_mg, 4),
                    },
                }
            )

        dishes_out.append({"standard_name": str(dish.get("standard_name") or ""), "ingredients": ing_out})

    meal_summary_in = llm_result.get("meal_summary") or {}
    advice = str(meal_summary_in.get("advice") or "")

    return {
        "meal_summary": {
            "total_energy_kj": round(total_energy_kj, 4),
            "net_weight_g": round(total_weight_g, 4),
            "advice": advice,
        },
        "captured_labels": labels,
        "dishes": dishes_out,
        "user_note_process": str(llm_result.get("user_note_process") or ""),
    }


