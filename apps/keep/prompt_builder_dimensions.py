def build_keep_dimensions_prompt(user_note: str) -> str:
    return f"""
你是一个专业的 Keep 身体围度解析助手。请分析这张图片，建立身体围度数据。

用户备注: {user_note}

请注意：
1. 提取所有可见的围度数据（胸围、腰围、臀围、大腿、小腿、手臂等）。
2. 单位通常为厘米(cm)。
3. 请输出为 JSON 格式。
"""
