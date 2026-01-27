"""
Diet Context Provider.

Aggregates user context (profile, today's intake) for diet advice.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# Pylint: standard imports before third party.
# But 'libs' is first party in this repo, effectively.
# Pylint treats 'libs' as third party if not configured?
# Actually 'pathlib' is standard, 'libs' is first party.
# 'apps' is first party.
from libs.core.config_loader import load_json
from libs.core.project_paths import get_project_root
from apps.common.record_service import RecordService
from apps.profile.service import ProfileService
from apps.common.user_bio_service import UserBioService
from apps.common.utils import parse_occurred_at, format_diet_records_to_table

def _diet_user_dir(user_id: str) -> Path:

    root = get_project_root()
    safe_user = user_id.strip() if user_id and user_id.strip() else "no_user_id"
    return root / "user_data" / safe_user / "diet"


def _calculate_today_so_far(
    user_id: str, 
    target_date: Optional[str] = None,
    ignore_record_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    从 RecordService 计算今天(或指定日期)已确认的记录汇总。
    exclude_record_id: 如果提供，在计算时排除该 ID (通常是因为正在编辑该记录的最新版 draft)
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
        # [Filter] 排重逻辑
        if ignore_record_id and rec.get("record_id") == ignore_record_id:
            continue

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


def get_context_bundle(
    user_id: str, 
    target_date: Optional[str] = None,
    ignore_record_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    从 user_data/<user_id>/ 读取背景数据：
    - ProfileService -> user_target（用户目标配置）
    - RecordService -> today_so_far
    ignore_record_id: 传递给 _calculate_today_so_far 和 history filter，防止正在编辑的卡片数据与已存档数据重复。
    """
    # 1. 获取 Profile (Target)
    profile = ProfileService.load_profile(user_id)
    
    user_target = {}
    if profile.diet:
        # 展平 diet target 结构
        user_target = profile.diet.model_dump()
        # 移除不需要的字段（如 energy_unit）
        user_target.pop("energy_unit", None)
    
    # 2. 动态计算 today_so_far (Apply Filter)
    today_so_far = _calculate_today_so_far(
        user_id=user_id, 
        target_date=target_date, 
        ignore_record_id=ignore_record_id
    )

    # 3. 获取 User Bio (长期记忆)
    user_bio = UserBioService.load_bio(user_id)

    # 4. 获取 Recent History (仅最近 3 天，且在 Provider 层预处理为精简文本)
    # 计算日期范围 (Focus on immediate context)
    end_date_obj = datetime.now()
    if target_date:
        try:
            dt = parse_occurred_at(target_date)
            if dt:
                end_date_obj = dt
        except Exception:
            pass

    # [Optimization] 只取最近 3 天，避免 token 浪费和无关历史干扰
    start_date_obj = end_date_obj - timedelta(days=3)
    start_str = start_date_obj.strftime("%Y-%m-%d")
    end_str = end_date_obj.strftime("%Y-%m-%d")

    raw_records = RecordService.get_unified_records_range(
        user_id=user_id, start_date=start_str, end_date=end_str
    )

    # [Optimization] 在 Context 层直接完成格式化，输出为精简的文本行列表
    # 格式: {"occurred_at": "...", "line_str": "YYYY-MM-DD|...", "record_id": "..."}
    formatted_recent_history = []
    
    # Tool: Use shared formatter

    # 简单调用 Utils 方法逐个格式化，保留 occurred_at 映射关系用于后续过滤
    for rec in raw_records:
        # [Filter] History Table Deduplication
        if ignore_record_id and rec.get("record_id") == ignore_record_id:
            continue
            
        # format_diet_records_to_table expects a list
        rows = format_diet_records_to_table([rec], as_list=True)
        for row in rows:
            formatted_recent_history.append({
                "occurred_at": rec.get("occurred_at"),
                "line_str": row
            })

    # 5. 构造返回结果
    out = {
        "user_target": user_target,
        "today_so_far": today_so_far,
        "user_bio": user_bio,
        "recent_history": formatted_recent_history,
        "meta": {"source": "user_data", "history_range": f"{start_str} to {end_str}"},
    }

    return out
