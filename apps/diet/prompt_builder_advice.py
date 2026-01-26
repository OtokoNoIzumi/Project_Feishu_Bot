"""
Diet Advice Prompt Builder.

Constructs prompts for generating dietary advice based on analysis results,
user context, and current time scenarios.
"""

import json
from datetime import datetime
from typing import Any, Dict, List


def _get_meal_time_range(diet_time: str) -> tuple[int, int]:
    """获取餐食的时间范围（小时）"""
    ranges = {
        "breakfast": (6, 10),
        "lunch": (10, 14),
        "dinner": (17, 22),
        "snack": (14, 17),  # 下午加餐
    }

    return ranges.get(diet_time, (0, 24))




def _determine_scenario_for_analysis(facts: Dict[str, Any], hour: int) -> str:
    """
    判断分析模式下的场景（已用餐状态）。
    """
    meal_summary = facts.get("meal_summary") or {}
    diet_time = meal_summary.get("diet_time")
    
    meal_names = {
        "breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐",
    }
    meal_name = meal_names.get(diet_time, "餐食")

    # 既然有 analyze 数据，说明用户至少拍了/录了
    return f"用户主要询问关于本次【{meal_name}】的建议。请点评其营养质量，并给出今天后续的互补建议。"


def _determine_scenario_for_chat(hour: int) -> str:
    """
    判断聊天模式下的场景。
    """
    if 6 <= hour < 10:
        return "现在是早上，用户需要全天饮食规划建议（早/午/晚/加餐的宏量分配）。"
    if 10 <= hour < 14:
        return "现在是中午，用户需要午餐选品建议和后续规划。"
    if 14 <= hour < 18:
        return "现在是下午，用户需要加餐建议（优先补什么）。"
    if 18 <= hour < 22:
        return "现在是晚上，用户需要晚餐选品建议（控制什么）。"
    return "现在是深夜，用户需要今日复盘和明日建议。"


def build_independent_chat_prompt(
    context_bundle: Dict[str, Any], 
    user_input: str,
    recent_messages: List[Any] = [],
    incremental_records: List[Dict[str, Any]] = []
) -> str:
    """
    构建【独立顾问模式】Prompt (Chat Mode)。
    
    设计理念：
    1. System Principles (Status Priority)
    2. Static Context (Bio, Target, Today)
    3. Full History Reference (Table)
    4. Dialogue History (Past)
    5. **Incremental Info** (New records since last dialogue)
    6. Current Interaction
    """
    # 1. 提取 Context
    user_target = context_bundle.get("user_target", {})
    today_so_far = context_bundle.get("today_so_far", {})
    user_bio = context_bundle.get("user_bio", [])
    recent_history = context_bundle.get("recent_history", [])

    # 2. 格式化板块
    bio_str = "\n".join([f"- {item}" for item in user_bio]) if user_bio else "暂无显性画像"
    
    # [Fix] History and Incremental records are passed as LIST OF STRINGS (pre-formatted)
    # So we just need to join them and add the header.
    
    table_header = "日期|餐|菜品|重量g|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g\n" + "-" * 80
    
    # A. Full History Table (最近20条)
    # recent_history is now List[str]
    recent_slice = recent_history[-20:] if recent_history else []
    if recent_slice:
        history_str = table_header + "\n" + "\n".join(recent_slice)
    else:
        history_str = "暂无记录"
    
    # B. Incremental Info Table
    # incremental_records is now List[str]
    incremental_str = "（无新增记录）"
    if incremental_records:
        # Check if items are strings (expected) or dicts (fallback safety)
        inc_lines = []
        for item in incremental_records:
            if isinstance(item, str):
                inc_lines.append(item)
            elif isinstance(item, dict):
                 # Fallback: if somehow a dict slipped through, assume it has 'line_str' or is raw
                 # This shouldn't happen based on Advice logic, but safety first.
                 inc_lines.append(str(item.get("line_str", item)))
        
        if inc_lines:
             incremental_str = table_header + "\n" + "\n".join(inc_lines)

    target_str = json.dumps(user_target, ensure_ascii=False)
    today_str = json.dumps(today_so_far, ensure_ascii=False, indent=2)

    # 3. 格式化对话历史
    # 注意：对话历史中可能包含旧的"状态"讨论，需提示 LLM 忽略旧状态
    dialogue_str = "（暂无历史消息）"
    if recent_messages:
        dialogue_lines = []
        for msg in recent_messages:
            role = "USER" if msg.role == "user" else "AI"
            content = msg.content or ""
            # Truncate content slightly less aggressive
            if len(content) > 300:
                content = content[:300] + "..."
            dialogue_lines.append(f"[{role}]: {content}")
        dialogue_str = "\n".join(dialogue_lines)

    # 4. 确定场景
    now = datetime.now()
    hour = now.hour
    scenario_hint = _determine_scenario_for_chat(hour)

    return f"""你是一位专业的、懂人性的营养顾问教练。
你正在与用户进行自由对话（Independent Mode）。

【重要原则】
1. **状态唯一性**：请以【LATEST REAL-TIME STATUS】中的数据为准。对话历史（Dialogue History）中提到的"刚才缺xx蛋白"如果与 Real-Time Status 冲突，请以 Real-Time Status 为准（因为用户可能刚吃完并更新了记录）。
2. **记忆维护**：捕捉关键的用户偏好变化。
3. **输出格式**：Strict JSON.

【LATEST REAL-TIME STATUS (The Source of Truth)】
>> 用户画像 (Bio):
{bio_str}

>> 今日目标 (Target):
{target_str}

>> 今日已摄入 (Today So Far):
{today_str}

>> 最近饮食记录 (Recent History Table - Full Reference):
{history_str}

【DIALOGUE HISTORY (Context)】
{dialogue_str}


【新增信息 (Incremental Information)】
(以下是自上次对话结束后，用户新增提交的饮食记录。Dialogue History 未包含这些信息，请将其视为最新的客观变化)
{incremental_str}


【Start Interaction】
【场景提示 (Time: {hour}:00)】
{scenario_hint}
USER Input: {user_input}

请根据最新状态(今日已摄入 + 新增信息)回答用户。直接输出 JSON。
"""


def build_diet_advice_prompt(
    facts: Dict[str, Any], context_bundle: Dict[str, Any], user_input: str = ""
) -> str:
    """
    构建【分析伴随模式】Prompt (Analysis Critique Mode)。
    
    目标：点评具体的 Analyze 结果。
    注意：此模式目前仍使用 Text 输出（为了兼容现有逻辑），
         如果将来要升级为 JSON，需同步修改 Usecase。
    """
    # 1. 提取 Context
    user_target = context_bundle.get("user_target", {})
    today_so_far = context_bundle.get("today_so_far", {})
    user_bio = context_bundle.get("user_bio", [])
    recent_history = context_bundle.get("recent_history", [])

    # 2. 确定场景
    now = datetime.now()
    hour = now.hour
    scenario_desc = _determine_scenario_for_analysis(facts, hour)

    # 3. 格式化
    bio_str = "\n".join([f"- {item}" for item in user_bio]) if user_bio else "暂无显性画像"
    
    today_so_far = context_bundle.get("today_so_far", {})
    
    # [Fix] History is already List[str] from ContextProvider
    table_header = "日期|餐|菜品|重量g|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g\n" + "-" * 80
    
    recent_slice = recent_history[-20:] if recent_history else []
    if recent_slice:
        history_str = table_header + "\n" + "\n".join(recent_slice)
    else:
        history_str = "暂无记录"
    
    ctx_str = json.dumps({
        "user_target": user_target,
        "today_so_far": today_so_far,
    }, ensure_ascii=False, indent=2)


    # 动态调整 Facts 的引导语，避免 LLM 误解为重复记录
    is_saved = facts.get("isSaved")
    extra_image_summary = facts.get("extra_image_summary")
    new_facts = facts.copy()
    new_facts.pop("extra_image_summary", None)
    new_facts.pop("isSaved", None)
    new_facts.pop("occurred_at", None)
    meal_facts_str = json.dumps(new_facts or {}, ensure_ascii=False, indent=2)

    if is_saved:
        facts_title = "【当前聚焦的记录详情 (Current Record Detail)】"
        facts_note = "(注意：此记录**已包含**在上方 Recent History 表格中。此处提供其详细原料信息，请基于此详情进行点评，切勿重复计数。)"
    else:
        facts_title = "【本次餐食数据 (Pending Draft)】"
        facts_note = "(注意：此记录**尚未**存入 History。请将其作为新增摄入，结合 History 中的已有数据进行评估。)"

    user_input_part = ""
    if user_input and user_input.strip():
        user_input_part = f"\n【用户直接输入】\n{user_input.strip()}\n"
    if extra_image_summary:
        user_input_part += f"\n【从用户上传图片识别出来的信息】\n{extra_image_summary}\n"

    return f"""你是一位懂训练与营养的教练型营养顾问。

【场景】
{scenario_desc}

【任务】
1) 点评本次餐食的营养质量（基于 dishes/meal_summary 数据）
2) 结合用户目标和今日已确认记录的累计进度，给出当天后续餐食的建议
3) 如果用户直接输入包括疑问，也进行解答

【关于用户的一些记忆】
{bio_str}

【当前营养状态】
{ctx_str}

>> 最近饮食记录:
{history_str}

{facts_title}
{facts_note}
{meal_facts_str}
{user_input_part}

要求：
- 像个记得用户的朋友一样聊天，所以不要直接指出自己使用了哪些数据、也不用上来自我介绍
- 你可以在综合考虑到饮食多样性和适合的情况下，在有必要的情况下结合最近的饮食记录和关于用户的记忆给出建议
- 建议要可执行、可量化（例如下一餐优先补蛋白多少克、减少哪些高脂来源）
- 输出自然的中文文本。
-【关于用户记忆的使用规范（最高优先级）】
你拥有用户的偏好记忆，请务必将这些信息作为决策的幕后逻辑，而不是对话的台词。
严禁显性引用：绝对不要使用“既然你喜欢……”、“记得你偏好……”、“考虑到你有……习惯”这类句式。
表现“默契”而非“记忆力”：要把这些偏好当作你们之间已知的共识（默契）。直接给出符合偏好的建议，而不需要解释“为什么符合你的偏好”。
Few-Shot 示例：
Bad (显性)：“因为你喜欢马蹄和蒸菜，所以我推荐马蹄蒸肉饼。”
Good (默契)：“中午哪怕忙，也可以弄个马蹄蒸肉饼，清脆爽口还能补蛋白。”（直接给结果，就像朋友知道你爱吃，自然会点这道菜，而不会特意强调是因为你爱吃）
"""
