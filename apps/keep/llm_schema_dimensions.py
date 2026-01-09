"""
Keep 身体围度数据的结构化输出 schema。

约定：
- 单位统一为 cm
"""

KEEP_DIMENSIONS_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "body_measure_event": {
            "type": "object",
            "properties": {
                "measured_at_local": {"type": "string", "description": "测量时间/日期"},
                "chest_cm": {"type": "number", "description": "胸围(cm)"},
                "waist_cm": {"type": "number", "description": "腰围(cm)"},
                "hips_cm": {"type": "number", "description": "臀围(cm)"},
                "thigh_cm": {"type": "number", "description": "大腿围(cm)"},
                "calf_cm": {"type": "number", "description": "小腿围(cm)"},
                "arm_cm": {"type": "number", "description": "手臂围(cm)"},
                "shoulder_cm": {"type": "number", "description": "肩宽(cm)"},
            },
            "required": [],
        }
    },
    "required": ["body_measure_event"],
}
