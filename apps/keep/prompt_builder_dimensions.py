"""
Keep Dimensions Prompt Builder.
"""

from apps.keep.body_metrics_schema import (
    build_metrics_schema_text_full,
    build_metrics_schema_text_limited,
)


def build_keep_dimensions_prompt(
    user_note: str, use_limited: bool = False
) -> str:
    """Build the prompt for parsing Keep dimensions screenshots."""
    metrics_schema_text = (
        build_metrics_schema_text_limited() if use_limited
        else build_metrics_schema_text_full()
    )
    return f"""
你是一个专业的 Keep 身体围度解析助手。请分析输入图片，建立身体围度数据。

Metrics Schema (字段需严格遵循):
{metrics_schema_text}

用户备注: {user_note}

请注意：
1. 提取所有可见的围度数据，并严格使用 Schema 中的字段名。
2. 单位通常为厘米(cm)，体重为公斤(kg)。
3. 请输出为 JSON 格式。
"""
