"""
Keep 体脂秤/身体成分报告的结构化输出 schema（用于 Gemini response_schema）。

约定：
- 只提取截图中可见的数值事实
- 输出以固定单位呈现：kg / % / kcal/day
"""

KEEP_SCALE_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "scale_event": {
            "type": "object",
            "properties": {
                "measured_at_local": {"type": "string", "description": "截图中可见的测量时间（本地时间字符串），不可见则空字符串"},
                "weight_kg": {"type": "number", "description": "体重（kg）"},
                "body_fat_pct": {"type": "number", "description": "体脂率（%）"},
                "bmi": {"type": "number", "description": "BMI"},
                "bmr_kcal_per_day": {"type": "number", "description": "基础代谢（kcal/day）"},
                "muscle_kg": {"type": "number", "description": "肌肉量（kg）"},
                "visceral_fat_level": {"type": "number", "description": "内脏脂肪等级（无单位，通常为数值等级）"},
                "subcutaneous_fat_pct": {"type": "number", "description": "皮下脂肪率（%）"},
                "protein_pct": {"type": "number", "description": "蛋白质（%）"},
                "skeletal_muscle_pct": {"type": "number", "description": "骨骼肌率（%）"},
                "fat_free_mass_kg": {"type": "number", "description": "去脂体重/瘦体重（kg）"},
                "water_pct": {"type": "number", "description": "水分（%）"},
                "bone_mass_kg": {"type": "number", "description": "骨量（kg）"},
                "body_score": {"type": "number", "description": "身体得分（分）"},
                "body_age_years": {"type": "number", "description": "身体年龄（岁）"},
            },
            "required": ["measured_at_local", "weight_kg"],
        }
    },
    "required": ["scale_event"],
}



