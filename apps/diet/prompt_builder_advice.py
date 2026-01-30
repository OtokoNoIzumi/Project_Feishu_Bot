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

【重要原则】
1. **状态唯一性**：请以【LATEST REAL-TIME STATUS】中的数据为准。对话历史（Dialogue History）中提到的"刚才缺xx蛋白"如果与 Real-Time Status 冲突，请以 Real-Time Status 为准（因为用户可能刚吃完并更新了记录）。
2. **记忆维护**：捕捉关键的用户偏好变化。
3. **输出格式**：Strict JSON.

【关于用户的一些记忆】
{bio_str}

【今日目标】
{target_str}

【今日已摄入】
{today_str}

>> 最近饮食记录:
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

请根据最新状态(今日已摄入 + 新增信息)回答用户。
"""


def build_diet_advice_prompt(
    facts: Dict[str, Any], context_bundle: Dict[str, Any], user_input: str = ""
) -> Dict[str, str]:
    """
    构建【分析伴随模式】Prompt (Analysis Critique Mode).
    
    返回字典:
    {
        "system": system_instruction,
        "user": user_content
    }
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
    
    # [History formatting]
    table_header = "日期|餐|菜品|重量g|能量kJ|蛋白g|脂肪g|碳水g|钠mg|纤维g\n" + "-" * 80
    
    # recent_history is List[str]
    recent_slice = recent_history[-20:] if recent_history else []
    if recent_slice:
        history_str = table_header + "\n" + "\n".join(recent_slice)
    else:
        history_str = "暂无记录"
    
    # Nutrition Status JSON
    ctx_str = json.dumps({
        "user_target": user_target,
        "so_far_before_meal": today_so_far,
    }, ensure_ascii=False, indent=2)

    # Current Facts JSON
    extra_image_summary = facts.get("extra_image_summary")
    new_facts = facts.copy()
    new_facts.pop("extra_image_summary", None)
    new_facts.pop("occurred_at", None)
    meal_facts_str = json.dumps(new_facts or {}, ensure_ascii=False, indent=2)
    
    # User Direct Input & Image Summary
    user_input_part = ""
    if user_input and user_input.strip():
        user_input_part = f"\n【用户直接输入】\n{user_input.strip()}\n"
    if extra_image_summary:
        user_input_part += f"\n【从用户上传图片识别出来的信息】\n{extra_image_summary}\n"

    # --- System Prompt Construction ---
    system_prompt = """你是一位深谙训练与营养科学的资深教练，也是用户生活中的一位“懂行老友”。

【核心人设】
- **角色**：你不是只会读数据的分析师，而是陪用户实战的战友。
- **语气**：口语化、自然、干练、懂生活。
- **禁忌**：
  - 严禁使用“📊 营养分析”、“🥗 建议”等分段标题。
  - 严禁使用教科书式的形容词（如“教科书式”、“极致低脂”、“宏观配比”）。
  - **严禁使用中二/军事词汇**：如“战术价值”、“精准狙击”、“查漏补缺”、“营养闭环”。
  - 严禁自我介绍或透露数据来源。
  - **严禁**使用死板的标题（如“📊 营养分析”），请使用更生活化的表达。

【任务逻辑】
请基于用户的本次进食数据，结合其目标和历史习惯，在一个自然的对话流中完成以下动作：

1.  **“老友式”点评（自然聊天）**：
    - 先回应用户的直接吐槽或感受（如不喜欢某种食物），但别讲大道理。
    - 快速扫描营养亮点（如纤维高、食材净、脂肪控制好），用肯定的语气点出来。
    - **【历史一致性校验】**：
      - 在评价“低摄入”（如早餐蛋白少）时，先检索“最近饮食记录”。
      - **若符合习惯**（如午晚大吃）：严禁解释“虽然低但符合习惯”或安抚“没关系”。**必须**结合这个习惯和全局的结果来衡量单餐，而不是纯粹剥离的看单餐数值和总数值的比例。
      - **若违背习惯**（如平时猛吃今天断食）：才进行提醒或询问。

2.  **下一步怎么吃（结构化但口语化）**：
    - **【默契推荐】**：
      - 直接推荐符合用户偏好（食材、做法）的菜品。
      - **Show, Don't Tell**：严禁解释推荐理由（如“因为你喜欢马蹄...”）。直接说：“中午整一个马蹄蒸肉饼吧”。

【回复结构规范】
请将回复整合成**1-2个自然的段落**。
- 第一部分：回应用户 + 顺带点评当前餐食。
- 第二部分：基于剩余指标，直接给出下一餐的“爽吃”建议或补救方案。

【排版与视觉规范（Markdown ）】
为了保证信息在网页端经过markdown插件渲染后清晰易读，请严格执行以下排版标准：

1.  **分层结构**：
    - **第一部分（点评）**：使用自然段落，像聊天一样。
    - **第二部分（建议）**：使用 **Markdown 列表**（1. / 2.）展示具体的执行方案。
    - **小标题**：建议部分请使用 **### 小标题**（例如 `### 接下来的安排`），保持结构清晰。

2.  **高亮重点（关键）**：
    - 所有的 **推荐菜品**（如 **马蹄蒸肉饼**）必须加粗。
    - 所有的 **建议重量**（如 **200g**）必须加粗。
    - 所有的 **关键营养素**（如 **100g 蛋白质**）必须加粗。"""

    # --- User Prompt Construction ---
    user_prompt = f"""【场景】
{scenario_desc}

【关于用户的一些记忆】
{bio_str}

>> 最近饮食记录:
{history_str}

【餐前营养状态】
{ctx_str}

【本次餐食数据 (Current/New Input)】
{meal_facts_str}

{user_input_part}
"""

    return {
        "system": system_prompt,
        "user": user_prompt
    }
