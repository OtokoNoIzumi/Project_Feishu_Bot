"""
Keep Scale Prompt Builder.
"""


def build_keep_scale_prompt(user_note: str = "") -> str:
    """Build the prompt for parsing Keep scale screenshots."""
    user_note_emphasis = ""
    if user_note and user_note.strip():
        user_note_emphasis = f"""
【用户输入（可选补充，仅供理解）】
{user_note.strip()}
"""

    return f"""你是一位严谨的数据抽取员。你的任务是把 Keep 体脂秤/身体成分报告截图中的数值信息提取为结构化 JSON。
{user_note_emphasis}
【要求】
1) 只提取截图里能明确看到的数字与含义；不要推测、不要生成建议、不要做健康结论。
2) 单位统一：
   - 体重/肌肉/骨量/去脂体重：kg
   - 各种比例：%
   - 基础代谢：kcal/day
3) 时间：如果截图中能看到测量时间，填入 measured_at_local；看不到则填空字符串。
4) 输出必须严格符合给定 JSON Schema，不要输出任何额外字段。
"""
