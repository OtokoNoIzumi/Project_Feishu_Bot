import json
from datetime import datetime
from typing import Any, Dict


def _get_meal_time_range(diet_time: str) -> tuple[int, int]:
    """获取餐食的时间范围（小时）"""
    ranges = {
        "breakfast": (6, 10),
        "lunch": (10, 14),
        "dinner": (17, 22),
        "snack": (14, 17),  # 下午加餐
    }
    return ranges.get(diet_time, (0, 24))


def _determine_scenario_without_analyze(hour: int) -> str:
    """没有 analyze 数据时，按当前时间判断场景（规划状态）"""
    if 6 <= hour < 10:
        return "现在是早上，用户正在规划一天的饮食。请基于用户目标与今日进度，给出全天饮食规划建议（早/午/晚/加餐的宏量分配与食物选择建议）。"
    elif 10 <= hour < 14:
        return "现在是中午，用户正在规划午餐。请基于用户目标与今日进度，给出午餐的选品建议和后续餐食的规划。"
    elif 14 <= hour < 18:
        return "现在是下午，用户正在规划加餐。请基于今日进度给出加餐建议（优先补什么、避免什么）。"
    elif 18 <= hour < 22:
        return "现在是晚上，用户正在规划晚餐。请基于今日进度给出晚餐选品建议（优先补什么、控制什么）。"
    else:
        return "现在是深夜/凌晨，用户可能在做全天回顾。请总结今日饮食与目标的匹配度，并给出明天的改进建议。"


def _determine_scenario_with_analyze(facts: Dict[str, Any], hour: int) -> str:
    """
    有 analyze 数据时，根据 diet_time 和当前时间判断场景（已用餐状态）

    如果 analyze 里有 diet_time，以它为准判断"该餐前/后"
    """
    meal_summary = facts.get("meal_summary") or {}
    diet_time = meal_summary.get("diet_time")

    meal_names = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }

    # 如果有 diet_time，以它为准判断"该餐前/后"
    if diet_time and diet_time in meal_names:
        start_hour, end_hour = _get_meal_time_range(diet_time)
        meal_name = meal_names[diet_time]

        # 判断是"该餐前"还是"该餐后"
        if start_hour <= hour < end_hour or (hour >= end_hour and hour < end_hour + 2):
            # 在该餐时间范围内或刚过（2小时内）：该餐后（已用餐）
            return f"用户已用{meal_name}。请点评本次{meal_name}的营养质量，并给出后续餐食的调整建议。"
        else:
            # 还没到该餐时间：该餐前（规划该餐）
            return f"用户正在规划{meal_name}。请基于用户目标与今日进度，给出{meal_name}的选品建议和后续餐食的规划。"
    else:
        # 没有 diet_time，按当前时间判断场景，但明确是"已用餐"状态
        if 6 <= hour < 10:
            return "现在是早上，用户已用餐。请点评本次餐食的营养质量，并给出今天后续餐食的规划建议。"
        elif 10 <= hour < 14:
            return "现在是中午，用户已用餐。请点评本次餐食的营养质量，并给出下午/晚上的调整建议。"
        elif 14 <= hour < 18:
            return "现在是下午，用户已用餐。请点评本次餐食的营养质量，并给出后续加餐/晚餐的建议。"
        elif 18 <= hour < 22:
            return "现在是晚上，用户已用餐。请点评本次餐食的营养质量，并给出今天的总结和明天的改进建议。"
        else:
            return "现在是深夜/凌晨，用户已用餐。请总结今日饮食与目标的匹配度，并给出明天的改进建议。"


def build_diet_advice_prompt(
    facts: Dict[str, Any], context_bundle: Dict[str, Any], user_input: str = ""
) -> str:
    """
    advice 的整体目标：根据一天的餐食进度和营养进度提供建议和反馈。

    输入结构：
    1. context_bundle（由 user_id 获取）：
       - user_target：用户目标配置
       - today_so_far：今日已确认记录的累计进度（不包含当前 analyze 的数据）
    2. facts（analyze 的完整结果）：
       - meal_summary：本次餐食汇总（能量、净重、可能的 diet_time）
       - dishes：本次餐食的详细构成
       - captured_labels：OCR 的营养成分表数据
       - extra_image_summary：图片中未被结构化字段覆盖的额外视觉信息（可能有也可能没有）
    3. user_input（用户直接输入）：
       - user_note + extra_image_summary 的组合

    输出要求：
    - 根据一天的餐食进度和营养进度提供建议和反馈
    - 如果包括 analyze 的数据，要额外点评当前餐食的情况
    - 如果用户直接输入包括疑问，也进行解答
    - 结合目的和当前一天的营养情况做一些当天后续餐食的建议
    """
    now = datetime.now()
    hour = now.hour

    # 判断是否有 analyze 数据
    has_analyze_data = bool(facts.get("dishes")) or bool(facts.get("meal_summary"))

    if has_analyze_data:
        # 有 analyze 数据：判断是"该餐前"还是"该餐后"
        scenario_desc = _determine_scenario_with_analyze(facts, hour)
    else:
        # 没有 analyze 数据：按当前时间判断场景，是"规划"状态
        scenario_desc = _determine_scenario_without_analyze(hour)

    ctx_str = json.dumps(context_bundle or {}, ensure_ascii=False, indent=2)

    user_input_part = ""
    if user_input and user_input.strip():
        user_input_part = f"\n【用户直接输入】\n{user_input.strip()}\n"

    if has_analyze_data:
        # 有 analyze 数据：需要点评当前餐食 + 后续建议
        facts_str = json.dumps(facts or {}, ensure_ascii=False, indent=2)
        return f"""你是一位懂训练与营养的教练型营养顾问。

【场景】
{scenario_desc}

【任务】
1) 点评本次餐食的营养质量（基于 facts 中的 dishes/meal_summary 数据）
2) 如果用户直接输入包括疑问，也进行解答
3) 结合用户目标和今日已确认记录的累计进度，给出当天后续餐食的建议

【要求】
- 建议要可执行、可量化（例如下一餐优先补蛋白多少克、减少哪些高脂来源）
- 输出自然的中文文本，无需特定格式

【上下文（context）】
包含用户目标（user_target）和今日已确认记录的累计进度（today_so_far，不包含当前 analyze 的数据）：
{ctx_str}

【本次餐食数据（facts，来自 analyze）】
{facts_str}
{user_input_part}
"""
    else:
        # 没有 analyze 数据：只需要规划建议
        return f"""你是一位懂训练与营养的教练型营养顾问。

【场景】
{scenario_desc}

【任务】
1) 如果用户直接输入包括疑问，进行解答
2) 结合用户目标和今日已确认记录的累计进度，给出当天后续餐食的规划建议

【要求】
- 建议要可执行、可量化（例如下一餐优先补蛋白多少克、减少哪些高脂来源）
- 输出自然的中文文本，无需特定格式

【上下文（context）】
包含用户目标（user_target）和今日已确认记录的累计进度（today_so_far）：
{ctx_str}
{user_input_part}
"""
