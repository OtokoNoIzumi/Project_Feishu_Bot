"""
Diet LLM 结构化输出 schema（用于 Gemini response_schema）

原则：
- 只要求模型输出“可观测事实/合理推断”的字段（食材、重量、宏量营养、标签OCR）
- 总能量/净重等由代码后处理计算并补齐
"""

DIET_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "meal_summary": {
            "type": "object",
            "properties": {
                "advice": {"type": "string", "description": "简体中文饮食建议"},
                "diet_time": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"], "description": "餐食分组"},
            },
            "required": ["advice", "diet_time"],
        },
        "captured_labels": {
            "type": "array",
            "description": "从包装营养成分表 OCR 得到的金标准数据（每100g/ml）",
            "items": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "brand": {"type": "string", "description": "不可见则为空字符串"},
                    "variant": {"type": "string", "description": "不可见则为空字符串"},
                    "serving_size": {"type": "string", "enum": ["100g", "100ml", "per_pack"]},
                    "energy_value": {"type": "number", "description": "OCR 读取到的能量数值"},
                    "energy_unit": {"type": "string", "enum": ["Kcal", "KJ"]},
                    "protein_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "sodium_mg": {"type": "number"},
                    "fiber_g": {"type": "number"},
                    "custom_note": {"type": "string", "description": "用户对该产品的特殊备注（如密度、购买渠道等）"},
                },
                "required": [
                    "product_name",
                    "brand",
                    "variant",
                    "serving_size",
                    "energy_value",
                    "energy_unit",
                    "protein_g",
                    "fat_g",
                    "carbs_g",
                    "sodium_mg",
                    "fiber_g",
                ],
            },
        },
        "dishes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard_name": {"type": "string", "description": "标准化菜名（简体中文）"},
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name_zh": {"type": "string"},
                                "weight_g": {"type": "number"},
                                "weight_method": {
                                    "type": "string",
                                    "enum": ["subtraction_precise", "dish_ratio_estimate", "pure_visual_estimate"],
                                },
                                "data_source": {"type": "string", "enum": ["label_ocr", "generic_estimate"]},
                                "macros": {
                                    "type": "object",
                                    "properties": {
                                        "protein_g": {"type": "number"},
                                        "fat_g": {"type": "number"},
                                        "carbs_g": {"type": "number"},
                                        "sodium_mg": {"type": "number"},
                                        "fiber_g": {"type": "number"},
                                    },
                                    "required": ["protein_g", "fat_g", "carbs_g", "sodium_mg", "fiber_g"],
                                },
                            },
                            "required": ["name_zh", "weight_g", "weight_method", "data_source", "macros"],
                        },
                    },
                },
                "required": ["standard_name", "ingredients"],
            },
        },
        "extra_image_summary": {
            "type": "string",
            "description": "图片中未被结构化字段覆盖、但对建议生成有用的额外视觉信息。例如：烹饪方式（蒸/煮/炸/烤，如果standard_name未体现）、食物的新鲜度/成熟度、搭配的酱料/配菜（如果未在dishes中单独列出）、用餐环境线索等。如果图片信息已完全被结构化字段覆盖，则输出空字符串。",
        },
        "user_note_process": {"type": "string"},
        "occurred_at": {
            "type": "string",
            "description": "如果用户在输入中明确指定了进食时间（如'昨天中午'、'12月29日'），请将其转换为 'YYYY-MM-DD HH:MM:SS' 格式。如果未指定，请输出空字符串。",
        },
    },
    "required": ["meal_summary", "dishes", "occurred_at"],
}


