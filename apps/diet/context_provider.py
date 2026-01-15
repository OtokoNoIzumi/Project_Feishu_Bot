"""
Diet Context Provider.

Aggregates user context (profile, today's intake) for diet advice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

# Pylint: standard imports before third party.
# But 'libs' is first party in this repo, effectively.
# Pylint treats 'libs' as third party if not configured?
# Actually 'pathlib' is standard, 'libs' is first party.
# 'apps' is first party.
from libs.core.config_loader import load_json
from libs.core.project_paths import get_project_root
from apps.common.record_service import RecordService


def _diet_user_dir(user_id: str) -> Path:

    root = get_project_root()
    safe_user = user_id.strip() if user_id and user_id.strip() else "no_user_id"
    return root / "user_data" / safe_user / "diet"


def _demo_context() -> Dict[str, Any]:
    # Demo 值仅用于阶段3跑通两段式链路；后续用真实 profile/today_summary 替换即可
    return {
        "user_target": {
            "goal": "fat_loss",
            "daily_energy_kj_target": 6273.0,
            "protein_g_target": 110.0,
            "fat_g_target": 50.0,
            "carbs_g_target": 150.0,
            "sodium_mg_target": 2000.0,
        },
        "today_so_far": {
            "consumed_energy_kj": 0,
            "consumed_protein_g": 0,
            "consumed_fat_g": 0,
            "consumed_carbs_g": 0,
            "consumed_sodium_mg": 0,
            "consumed_fiber_g": 0,
            "activity_burn_kj": 0,
        },
        "meta": {"source": "demo_fallback"},
    }


def _calculate_today_so_far(user_id: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    从 RecordService 计算今天(或指定日期)已确认的记录汇总。
    """
    consumed_energy_kj = 0.0
    consumed_protein_g = 0.0
    consumed_fat_g = 0.0
    consumed_carbs_g = 0.0
    consumed_sodium_mg = 0.0
    consumed_fiber_g = 0.0
    activity_burn_kj = 0.0

    # 获取流水
    if target_date:
        records = RecordService.get_unified_records_by_date(user_id, target_date)
    else:
        records = RecordService.get_todays_unified_records(user_id)

    for rec in records:
        # 汇总 meal_summary
        meal = rec.get("meal_summary") or {}
        if isinstance(meal, dict):
            consumed_energy_kj += float(meal.get("total_energy_kj") or 0.0)

        # 汇总 dishes 的宏量
        for dish in rec.get("dishes") or []:
            if not isinstance(dish, dict):
                continue
            for ing in dish.get("ingredients") or []:
                if not isinstance(ing, dict):
                    continue
                macros = ing.get("macros") or {}
                consumed_protein_g += float(macros.get("protein_g") or 0.0)
                consumed_fat_g += float(macros.get("fat_g") or 0.0)
                consumed_carbs_g += float(macros.get("carbs_g") or 0.0)
                consumed_sodium_mg += float(macros.get("sodium_mg") or 0.0)
                consumed_fiber_g += float(macros.get("fiber_g") or 0.0)

        # TODO: activity_burn_kj 需要从 Keep 或其他运动数据源汇总

    return {
        "consumed_energy_kj": round(consumed_energy_kj, 4),
        "consumed_protein_g": round(consumed_protein_g, 4),
        "consumed_fat_g": round(consumed_fat_g, 4),
        "consumed_carbs_g": round(consumed_carbs_g, 4),
        "consumed_sodium_mg": round(consumed_sodium_mg, 4),
        "consumed_fiber_g": round(consumed_fiber_g, 4),
        "activity_burn_kj": round(activity_burn_kj, 4),
    }


def get_context_bundle(user_id: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    从 user_data/<user_id>/diet/ 读取背景数据（仅由 user_id 获取）：
    - profile.json -> user_target（用户目标配置）
    - RecordService -> today_so_far
    """
    base = _diet_user_dir(user_id)
    profile = load_json(base / "profile.json") if base.exists() else {}

    # 动态计算 today_so_far
    today_so_far = _calculate_today_so_far(user_id=user_id, target_date=target_date)

    # 如果 profile 和 today_so_far 都为空，回退 demo
    if not profile and sum(today_so_far.values()) == 0.0:
        demo = _demo_context()
        out = {
            "user_target": demo.get("user_target", {}),
            "today_so_far": demo.get("today_so_far", {}),
            "meta": {"source": "demo_fallback"},
        }
    else:
        demo = _demo_context()
        out = {
            "user_target": profile or demo.get("user_target", {}),
            "today_so_far": (
                today_so_far
                if sum(today_so_far.values()) > 0
                else demo.get("today_so_far", {})
            ),
            "meta": {"source": "user_data"},
        }

    return out
