"""
Keep Unified Prompt Builder.
"""

from datetime import datetime


def build_keep_unified_prompt(user_note: str) -> str:
    """Build the prompt for parsing unified Keep screenshots."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
你是一个专业的 Keep 健康数据解析助手。用户上传了一张或多张图片（可能是体重体脂报告、睡眠报告、或身体数据中心截图）。

请分析所有图片，尽可能提取出以下三类数据（如果存在）：
1. 体重/体脂数据 (Scale Event)
2. 睡眠数据 (Sleep Event)
3. 身体围度数据 (Body Dimensions Event)

用户备注: {user_note}

请注意：
- 如果某类数据不存在，列表留空即可。
- 【时间提取】：当前系统时间为 {current_time}。如果用户在备注中明确指定了时间（如“昨天”、“12月29日”），请基于系统时间推算准确的 'YYYY-MM-DD HH:MM:SS' 并填入 `occurred_at`。如果是实时记录或未指定，`occurred_at` 留空。
- 如果同一张图片包含多个维度（例如数据中心截图既有体重又有围度），请分别提取到对应的列表中。
- 如果有多张不相关的图片，请分别处理并汇总到列表中。
- 所有时间请尽可能解析为本地时间字符串。
- 请输出为符合 Schema 的 JSON 格式。
"""
