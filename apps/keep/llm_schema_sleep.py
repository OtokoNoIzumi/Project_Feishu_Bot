"""
Keep 睡眠监测报告的结构化输出 schema。

约定：
- 提取截图中可见的睡眠数据
- 时间均为本地时间字符串
- 时长统一转换为分钟
"""

KEEP_SLEEP_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "sleep_event": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "监测日期，如 '2023-10-27'",
                },
                "sleep_start_time": {
                    "type": "string",
                    "description": "入睡时间 (HH:MM)",
                },
                "sleep_end_time": {"type": "string", "description": "起床时间 (HH:MM)"},
                "total_duration_minutes": {
                    "type": "integer",
                    "description": "总睡眠时长(分钟)",
                },
                "score": {"type": "integer", "description": "睡眠评分"},
                "deep_sleep_minutes": {
                    "type": "integer",
                    "description": "深睡时长(分钟)",
                },
                "light_sleep_minutes": {
                    "type": "integer",
                    "description": "浅睡时长(分钟)",
                },
                "rem_sleep_minutes": {
                    "type": "integer",
                    "description": "快速眼动/REM时长(分钟)",
                },
                "awake_minutes": {"type": "integer", "description": "清醒时长(分钟)"},
                "awake_count": {"type": "integer", "description": "清醒次数"},
            },
            "required": ["total_duration_minutes", "score"],
        }
    },
    "required": ["sleep_event"],
}
