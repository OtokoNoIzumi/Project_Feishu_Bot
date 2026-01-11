from typing import Any, Dict, Optional


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _round_opt(v: Optional[float], ndigits: int = 4) -> Optional[float]:
    if v is None:
        return None
    return round(float(v), ndigits)


def finalize_scale_event(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    raw = llm_result.get("scale_event") or {}
    if not isinstance(raw, dict):
        raw = {}

    measured_at_local = str(raw.get("measured_at_local") or "").strip()

    out = {
        "measured_at_local": measured_at_local,
        "weight_kg": _round_opt(_to_float(raw.get("weight_kg")), 4) or 0.0,
        "body_fat_pct": _round_opt(_to_float(raw.get("body_fat_pct")), 4),
        "bmi": _round_opt(_to_float(raw.get("bmi")), 4),
        "bmr_kcal_per_day": _round_opt(_to_float(raw.get("bmr_kcal_per_day")), 4),
        "muscle_kg": _round_opt(_to_float(raw.get("muscle_kg")), 4),
        "visceral_fat_level": _round_opt(_to_float(raw.get("visceral_fat_level")), 4),
        "subcutaneous_fat_pct": _round_opt(
            _to_float(raw.get("subcutaneous_fat_pct")), 4
        ),
        "protein_pct": _round_opt(_to_float(raw.get("protein_pct")), 4),
        "skeletal_muscle_pct": _round_opt(_to_float(raw.get("skeletal_muscle_pct")), 4),
        "fat_free_mass_kg": _round_opt(_to_float(raw.get("fat_free_mass_kg")), 4),
        "water_pct": _round_opt(_to_float(raw.get("water_pct")), 4),
        "bone_mass_kg": _round_opt(_to_float(raw.get("bone_mass_kg")), 4),
        "body_score": _round_opt(_to_float(raw.get("body_score")), 4),
        "body_age_years": _round_opt(_to_float(raw.get("body_age_years")), 4),
    }

    # 清理 None 字段：保留 weight_kg 与 measured_at_local，其余缺失字段不输出
    cleaned = {
        "measured_at_local": out["measured_at_local"],
        "weight_kg": out["weight_kg"],
    }
    for k, v in out.items():
        if k in cleaned:
            continue
        if v is not None:
            cleaned[k] = v

    return {"scale_event": cleaned}
