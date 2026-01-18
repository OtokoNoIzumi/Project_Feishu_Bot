"""
Profile Analysis LLM Schema.
手动定义 JSON Schema，与 Diet/Keep 模块保持风格一致。

LLM 输出范围：
- advice: 分析建议
- suggested_diet_targets: 推荐的饮食目标数值（goal/energy_unit 等 UI 项不输出）
- suggested_keep_targets: 推荐的 Keep 目标（仅当有历史数据时才输出）
"""

# 围度目标字段定义（与 body_metrics_schema.py 保持一致）
DIMENSION_TARGET_PROPERTIES = {
    "bust": {
        "type": "number",
        "description": "目标胸围 (cm)",
    },
    "waist": {
        "type": "number",
        "description": "目标腰围 (cm)",
    },
    "hip_circ": {
        "type": "number",
        "description": "目标臀围 (cm)",
    },
    "arm": {
        "type": "number",
        "description": "目标上臂围 (cm)",
    },
    "thigh": {
        "type": "number",
        "description": "目标大腿围 (cm)",
    },
    "calf": {
        "type": "number",
        "description": "目标小腿围 (cm)",
    },
}


PROFILE_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "advice": {
            "type": "string",
            "description": "针对用户请求和数据的分析建议（Markdown格式，简体中文）。解释推算依据、预期时间等。",
        },
        "suggested_diet_targets": {
            "type": "object",
            "description": "推荐的饮食目标数值。基于 TDEE 和用户目标类型计算。",
            "properties": {
                "daily_energy_kj_target": {
                    "type": "integer",
                    "description": "每日热量目标 (kJ)",
                },
                "protein_g_target": {
                    "type": "integer",
                    "description": "每日蛋白质目标 (g)",
                },
                "fat_g_target": {
                    "type": "integer",
                    "description": "每日脂肪目标 (g)",
                },
                "carbs_g_target": {
                    "type": "integer",
                    "description": "每日碳水目标 (g)",
                },
                "sodium_mg_target": {
                    "type": "integer",
                    "description": "每日钠目标 (mg)",
                },
            },
            "required": [
                "daily_energy_kj_target",
                "protein_g_target",
                "fat_g_target",
                "carbs_g_target",
                "sodium_mg_target",
            ],
        },
        "suggested_keep_targets": {
            "type": "object",
            "description": "推荐的 Keep 目标。仅推算用户未设定且有历史数据的项。",
            "properties": {
                "weight_kg_target": {
                    "type": "number",
                    "description": "目标体重 (kg)",
                },
                "body_fat_pct_target": {
                    "type": "number",
                    "description": "目标体脂率 (%)",
                },
                "dimensions_target": {
                    "type": "object",
                    "description": "目标围度 (cm)。只推算有历史数据的维度。",
                    "properties": DIMENSION_TARGET_PROPERTIES,
                },
            },
            # 不设置 required，因为部分或全部可能不需要输出
        },
        "estimated_months": {
            "type": "integer",
            "description": "预估达成目标所需的月数。基于目标差值和每日热量缺口/盈余推算。",
        },
        "suggested_user_info": {
            "type": "string",
            "description": "用户关键主张的完整更新版本。综合现有 user_info 和用户本次输入中的新主张，输出完整的、最新的内容。如果没有变化，不输出此字段。",
        },
    },
    "required": ["advice", "suggested_diet_targets"],
    # suggested_keep_targets, estimated_months, suggested_user_info 不是必须的
}
