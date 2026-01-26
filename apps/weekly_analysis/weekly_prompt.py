"""
Weekly Analysis Prompt Builder V2.

Constructs the comprehensive prompt for weekly diet/keep analysis.
V2: 引入"侦探思维"和交叉归因分析
"""

import json
from datetime import date
from typing import Any, Dict, List

from apps.weekly_analysis.data_collector import WeeklyDataBundle
from apps.common.utils import format_diet_records_to_table



def _format_scale_records_for_prompt(
    records: List[Dict], baseline: Dict | None
) -> str:
    """
    Format scale records - compact table format with body composition.
    V2: 增加骨骼肌%、水分%、内脏脂肪 + 基线对比
    """
    if not records and not baseline:
        return "无体重记录"

    lines = ["日期|体重kg|体脂%|骨骼肌%|水分%|内脏脂肪|类型"]
    lines.append("-" * 60)

    # Helper to format row
    def fmt_row(rec, label):
        occurred = rec.get("occurred_at", "")[:10]
        weight = rec.get("weight_kg", "-")
        fat = rec.get("body_fat_pct", "-")
        skeletal_muscle = rec.get("skeletal_muscle_pct", "-")
        water = rec.get("water_pct", "-")
        visceral_fat = rec.get("visceral_fat_level", "-")
        return f"{occurred}|{weight}|{fat}|{skeletal_muscle}|{water}|{visceral_fat}|{label}"

    if baseline:
        lines.append(fmt_row(baseline, "基线"))

    for rec in records:
        lines.append(fmt_row(rec, "本周"))

    return "\n".join(lines)


def _format_dimension_data_for_prompt(
    current: List[Dict], baseline: Dict | None
) -> str:
    """Format dimension data - compact table format."""
    if not current and not baseline:
        return "无围度记录"

    lines = ["日期|胸围cm|腰围cm|臀围cm|大腿cm|小腿cm|手臂cm|类型"]
    lines.append("-" * 60)

    if baseline:
        d = baseline.get("occurred_at", "")[:10]
        chest = baseline.get("bust", "-")
        waist = baseline.get("waist", "-")
        hips = baseline.get("hip_circ", "-")
        thigh = baseline.get("thigh", "-")
        calf = baseline.get("calf", "-")
        arm = baseline.get("arm", "-")
        lines.append(f"{d}|{chest}|{waist}|{hips}|{thigh}|{calf}|{arm}|基线")

    for rec in current:
        d = rec.get("occurred_at", "")[:10]
        chest = rec.get("bust", "-")
        waist = rec.get("waist", "-")
        hips = rec.get("hip_circ", "-")
        thigh = rec.get("thigh", "-")
        calf = rec.get("calf", "-")
        arm = rec.get("arm", "-")
        lines.append(f"{d}|{chest}|{waist}|{hips}|{thigh}|{calf}|{arm}|本周")

    return "\n".join(lines)


def _format_dish_library_for_prompt(dishes: List[Dict], limit: int = 30) -> str:
    """
    Format dish library with nutritional data (per 100g).
    For meal planning suggestions.
    """
    if not dishes:
        return "无菜式库"

    # Header
    lines = ["菜品|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g (每100g)"]
    lines.append("-" * 70)

    # Take recent N dishes, dedupe by name
    seen_names = set()
    for dish in dishes[:limit * 2]:  # Read more to account for dupes
        name = dish.get("dish_name", "?")
        if name in seen_names:
            continue
        seen_names.add(name)

        if len(seen_names) > limit:
            break

        macros = dish.get("macros_per_100g", {})
        energy = macros.get("energy_kj", "-")
        protein = macros.get("protein_g", "-")
        fat = macros.get("fat_g", "-")
        carbs = macros.get("carbs_g", "-")
        sodium = macros.get("sodium_mg", "-")
        fiber = macros.get("fiber_g", "-")

        # Format numbers if they exist
        def fmt(v):
            if isinstance(v, (int, float)):
                return f"{v:.1f}"
            return str(v) if v else "-"

        lines.append(
            f"{name}|{fmt(energy)}|{fmt(protein)}|{fmt(fat)}|{fmt(carbs)}|{fmt(sodium)}|{fmt(fiber)}"
        )

    return "\n".join(lines)


def _calculate_daily_sodium_totals(records: List[Dict]) -> str:
    """计算每日钠摄入汇总，用于交叉分析"""
    if not records:
        return "无数据"

    daily_sodium = {}
    for rec in records:
        occurred = rec.get("occurred_at", "")[:10]
        if not occurred:
            continue

        if occurred not in daily_sodium:
            daily_sodium[occurred] = 0.0

        for dish in rec.get("dishes", []):
            for ing in dish.get("ingredients", []):
                macros = ing.get("macros", {})
                daily_sodium[occurred] += float(macros.get("sodium_mg", 0) or 0)

    lines = []
    for d, na in sorted(daily_sodium.items()):
        warning = " ⚠️高" if na > 2300 else ""
        lines.append(f"{d}: {na:.0f}mg{warning}")

    return "\n".join(lines)


def build_weekly_analysis_prompt(bundle: WeeklyDataBundle) -> str:
    """
    Build the comprehensive weekly analysis prompt.
    V2: 侦探思维 + 交叉归因分析

    Args:
        bundle: WeeklyDataBundle containing all collected data.

    Returns:
        Complete prompt string for AI analysis.
    """
    week_range = f"{bundle.week_start} 至 {bundle.week_end}"

    # Format data sections
    # Format data sections
    diet_data = format_diet_records_to_table(bundle.diet_records)
    scale_data = _format_scale_records_for_prompt(
        bundle.scale_records, bundle.baseline_scale_record
    )
    dimension_data = _format_dimension_data_for_prompt(
        bundle.current_week_dimensions, bundle.baseline_dimension
    )
    dish_library = _format_dish_library_for_prompt(bundle.dish_library)

    # 新增：钠摄入汇总（用于交叉分析）
    sodium_summary = _calculate_daily_sodium_totals(bundle.diet_records)

    # User profile and preferences
    profile_str = json.dumps(bundle.user_profile, ensure_ascii=False, indent=2) if bundle.user_profile else "无"
    preferences_str = json.dumps(bundle.user_preferences, ensure_ascii=False, indent=2) if bundle.user_preferences else "无"

    # Data counts for context
    summary = bundle.to_summary()
    diet_count = len(bundle.diet_records)
    dish_count = sum(len(r.get("dishes", [])) for r in bundle.diet_records)
    scale_count = summary["scale_record_count"]

    prompt = f"""## 角色设定
你是一位敏锐的**高级健康数据侦探**，擅长通过数据挖掘身体变化的真相。
你的风格是**一针见血、逻辑严密，同时具有同理心**。
拒绝通用的废话和"建议多喝水"这类空话，只提供基于数据的定制化洞察。
说话要有温度，像一个了解用户的私人教练。

## 任务
分析用户 {week_range} 这一周的饮食和身体数据，挖掘数据之间的因果联系。

## 分析核心逻辑（必须遵循）

### 第一步：交叉验证 - 真胖还是水肿？
- 看【饮食记录】中的每日钠摄入（已汇总在下方）
- 结合【体重记录】中的水分%和体重波动
- 判断体重变化是真实减脂还是水分波动

### 第二步：围度验证 - 揭穿体重数字的谎言
- 对比体重变化和围度变化
- 如果体重降但腰围涨，检查是否因晚餐过量导致腹部胀气
- 如果体重涨但腰围降，可能是肌肉增长或测量误差

### 第三步：行为归因 - 奖励好行为，指出失误
- 将好的结果归因于具体的正确行为（如："干蒸牛肉是掉秤的功臣"）
- 将坏的结果归因于具体的失误（如："水煮鱼的2000mg钠导致第二天水肿"）

## 用户画像与目标
{profile_str}

## 用户饮食偏好
{preferences_str}

## 本周数据

### 饮食记录 (共{diet_count}餐, {dish_count}道菜)
{diet_data}

### 每日钠摄入汇总（关键！与次日体重关联分析）
{sodium_summary}

### 身体数据 (共{scale_count}条)
{scale_data}

### 围度记录
{dimension_data}

### 菜式库 (供替换建议参考)
{dish_library}

## 输出要求

请严格遵循 JSON Schema 输出。特别注意：

1. **executive_summary.title**: 像新闻标题，要抓眼球，如"水肿警报：周末高盐晚餐的代价"
2. **key_insight**: 用"现象 → 数据证据 → 根本原因 → 可执行建议"的格式
3. **truth_about_weight**: 不要只说"体重下降了X斤"，要分析这是水分、脂肪还是肌肉
4. **highlight_moment & sabotage_event**: 具体到某一餐某一道菜
5. **tags**: 给菜品贴情绪化标签，如"减脂神器"、"钠盐炸弹"
6. **weekly_challenge**: 用游戏化的语言，激励用户

## 注意事项

- 不要只罗列数据，要告诉用户"为什么"
- 建议要可执行、可量化（如"将晚餐钠控制在1500mg内"而非"少吃盐"）
- 说话要有温度，可以偶尔用emoji
- 如果数据不足以得出结论，诚实说明
"""

    return prompt


# --- Alternative: Generate schema-compatible dict for Gemini ---

def get_analysis_json_schema() -> Dict[str, Any]:
    """
    Generate JSON schema compatible with Gemini's response_schema parameter.
    """
    from apps.weekly_analysis.analysis_schema import get_weekly_analysis_schema
    return get_weekly_analysis_schema()
