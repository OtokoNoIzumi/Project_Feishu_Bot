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
                "diet_time": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "餐食分组",
                },
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
                    "unit_weight_g": {
                        "type": "number",
                        "description": "单份/单包的实际重量（g）。例如用户备注'每份80g'，或者包装显示'净含量80g'。此字段用于预填用户的单次食用量，不影响营养成分表的计算基准。",
                    },
                    "table_unit": {
                        "type": "string",
                        "description": "营养成分表的表头单位。如 g, ml, 份。注意：仅提取单位字符串。",
                    },
                    "table_amount": {
                        "type": "number",
                        "description": "营养成分表的表头数值。例如 '100ml'->100, '1份'->1。不可为0。",
                    },
                    "density_factor": {
                        "type": "number",
                        "description": "换算系数。默认1.0。若serving为100ml且密度1.03，则填1.03（表示100ml=103g）。若serving为1勺且勺重25g，则填25（表示1勺=25g）,也就是用来把单位换算到重量的系数。",
                    },
                    "energy_value": {
                        "type": "number",
                        "description": "OCR 读取到的能量数值",
                    },
                    "energy_unit": {"type": "string", "enum": ["Kcal", "KJ"]},
                    "protein_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "sodium_mg": {"type": "number"},
                    "fiber_g": {"type": "number"},
                    "custom_note": {
                        "type": "string",
                        "description": "用户对该产品的特殊备注（如购买渠道等）",
                    },
                },
                "required": [
                    "product_name",
                    "brand",
                    "variant",
                    "table_unit",
                    "energy_value",
                    "energy_unit",
                    "protein_g",
                    "fat_g",
                    "carbs_g",
                    "sodium_mg",
                    "fiber_g",
                    "density_factor",
                    "table_amount",
                ],
            },
        },
        "dishes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard_name": {
                        "type": "string",
                        "description": "标准化菜名（简体中文）",
                    },
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name_zh": {"type": "string"},
                                "weight_g": {"type": "number"},
                                "weight_method": {
                                    "type": "string",
                                    "enum": [
                                        "subtraction_precise",
                                        "dish_ratio_estimate",
                                        "pure_visual_estimate",
                                    ],
                                },
                                "data_source": {
                                    "type": "string",
                                    "enum": ["label_ocr", "generic_estimate"],
                                },
                                "macros": {
                                    "type": "object",
                                    "properties": {
                                        "protein_g": {"type": "number"},
                                        "fat_g": {"type": "number"},
                                        "carbs_g": {"type": "number"},
                                        "sodium_mg": {"type": "number"},
                                        "fiber_g": {"type": "number"},
                                    },
                                    "required": [
                                        "protein_g",
                                        "fat_g",
                                        "carbs_g",
                                        "sodium_mg",
                                        "fiber_g",
                                    ],
                                },
                            },
                            "required": [
                                "name_zh",
                                "weight_g",
                                "weight_method",
                                "data_source",
                                "macros",
                            ],
                        },
                    },
                },
                "required": ["standard_name", "ingredients"],
            },
        },
        "extra_image_summary": {
            "type": "string",
            "description": (
                "图片中未被结构化字段覆盖、但对建议生成有用的额外视觉信息。"
                "例如：烹饪方式（蒸/煮/炸/烤，如果standard_name未体现）、"
                "食物的新鲜度/成熟度、搭配的酱料/配菜（如果未在dishes中单独列出）、"
                "用餐环境线索等。如果图片信息已完全被结构化字段覆盖，则输出空字符串。"
            ),
        },
        "user_note_process": {"type": "string"},
        "occurred_at": {
            "type": "string",
            "description": "如果用户在输入中明确指定了进食时间（如'昨天中午'、'12月29日'），请将其转换为 'YYYY-MM-DD HH:MM:SS' 格式。如果未指定，请输出空字符串。",
        },
    },
    "required": ["meal_summary", "dishes", "occurred_at"],
}

ADVISOR_CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply_text": {
            "type": "string",
            "description": "回复用户的文本内容。口语化、有温度，像专业的营养顾问一样沟通。",
        },
        "user_bio_update": {
            "type": "object",
            "description": "基于本次对话，需要对显性用户画像进行的增删操作。如果没有更新，该字段可为空。\n警告：严禁记录AI的建议（如'建议多吃蛋白'）或已有的结构化数据（如体重目标）。只记录用户明确表达的个人偏好/约束。",
            "properties": {
                "add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要新增的用户事实/偏好。例如：'用户不爱吃香菜'、'用户最近在进行低碳饮食'。禁止包含：'建议用户...'、'用户需要...'。",
                },
                "remove": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要移除的过时用户事实/偏好",
                },
            },
        },
    },
    "required": ["reply_text"],
}
