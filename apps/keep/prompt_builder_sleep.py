"""
Keep Sleep Prompt Builder.
"""


def build_keep_sleep_prompt(user_note: str) -> str:
    """Build the prompt for parsing Keep sleep screenshots."""
    return f"""
你是一个专业的 Keep 睡眠报告解析助手。请分析这张图片，提取睡眠数据。

用户备注: {user_note}

请注意：
1. 时长如果是 "8小时33分"，请转换为总分钟数 (8*60+33 = 513)。
2. 提取深睡、浅睡、REM、清醒的具体时长。
3. 请输出为 JSON 格式。
"""
