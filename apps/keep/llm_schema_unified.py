from apps.keep.llm_schema_scale import KEEP_SCALE_LLM_SCHEMA
from apps.keep.llm_schema_sleep import KEEP_SLEEP_LLM_SCHEMA
from apps.keep.llm_schema_dimensions import KEEP_DIMENSIONS_LLM_SCHEMA

"""
Keep 统一解析 Schema (Multi-Modal / Multi-Image)
允许在一个 Request 中包含多张图片，一次性提取所有可见的 Keep 事件。
"""

KEEP_UNIFIED_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "scale_events": {
            "type": "array",
            "description": "检测到的所有体重/体脂事件",
            "items": KEEP_SCALE_LLM_SCHEMA["properties"]["scale_event"],
        },
        "sleep_events": {
            "type": "array",
            "description": "检测到的所有睡眠事件",
            "items": KEEP_SLEEP_LLM_SCHEMA["properties"]["sleep_event"],
        },
        "body_measure_events": {
            "type": "array",
            "description": "检测到的所有身体围度测量事件",
            "items": KEEP_DIMENSIONS_LLM_SCHEMA["properties"]["body_measure_event"],
        },
    },
    "required": [],  # 允许为空，因为可能只传了某一种图片
}
