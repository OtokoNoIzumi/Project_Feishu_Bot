"""
Body Metrics Schema Definition & Metadata
用于定义身体围度数据的字段含义、单位、交互提示（备注）以及参考基准。
"""

from typing import Any, Dict, Iterable, Optional

METRICS_SCHEMA = {
    # --- Basic ---
    "height": {
        "name": "Height",
        "name_zh": "身高",
        "unit": "cm",
        "description": "User height.",
        "description_zh": "用户身高。"
    },
    # "weight": {
    #     "name": "Weight",
    #     "name_zh": "体重",
    #     "unit": "kg",
    #     "description": "User weight.",
    #     "description_zh": "用户体重。"
    # },

    # --- Upper Body ---
    "neck": {
        "name": "Neck",
        "name_zh": "颈围",
        "unit": "cm",
        "description": "Neck circumference.",
        "description_zh": "颈部最细处或喉结下方的围度。"
    },
    "bust": {
        "name": "Bust",
        "name_zh": "胸围",
        "unit": "cm",
        "description": "Measure around your chest at nipple level.",
        "description_zh": "通过乳头水平线的胸部围度。"
    },
    "bust_padded": {
        "name": "Bust (Padded)",
        "name_zh": "带义乳胸围",
        "unit": "cm",
        "description": "Padded measurement with Bra.",
        "description_zh": "穿戴文胸/义乳后的胸围测量值。"
    },
    "underbust": {
        "name": "Underbust (Band)",
        "name_zh": "下胸围",
        "unit": "cm",
        "description": "Measure around your chest underneath your breasts.",
        "description_zh": "乳房根部下方的胸部围度（用于确定罩杯底围）。"
    },
    "shoulder_circ": {
        "name": "Shoulder (Circ)",
        "name_zh": "肩围",
        "unit": "cm",
        "description": "Shoulder circumference.",
        "description_zh": "包含手臂及三角肌的肩部最大围度。"
    },
    "shoulder_width": {
        "name": "Shoulder (Width)",
        "name_zh": "肩宽",
        "unit": "cm",
        "description": "Width across, not circumference.",
        "description_zh": "两肩峰点之间的直线距离（非围度）。"
    },
    "arm": {
        "name": "Arm",
        "name_zh": "上臂围",
        "unit": "cm",
        "description": "Upper arm circumference (Biceps).",
        "description_zh": "上臂（大臂）肱二头肌最粗处的围度。"
    },
    "wrist": {
        "name": "Wrist",
        "name_zh": "手腕围",
        "unit": "cm",
        "description": "Circumference.",
        "description_zh": "手腕骨茎突处的围度。"
    },
    "forearm": {
        "name": "Forearm",
        "name_zh": "前臂围",
        "unit": "cm",
        "description": "Lower arm circumference below elbow.",
        "description_zh": "前臂（小臂）最粗处的围度。"
    },

    # --- Torso ---
    "ltorso": {
        "name": "LTorso",
        "name_zh": "坐姿躯干长",
        "unit": "cm",
        "description": "Seated Torso Length - Measure from below breast down to where you bend when you sit. Used for corsets in particular.",
        "description_zh": "坐姿测量：从乳房下缘垂直向下量到大腿根折叠处（通常用于束腰定制）。"
    },
    "waist": {
        "name": "Waist",
        "name_zh": "腰围",
        "unit": "cm",
        "description": "Waist circumference.",
        "description_zh": "腰部最细处（通常在肚脐上方）的围度。"
    },

    # --- Lower Body ---
    "upper_hip": {
        "name": "Upper Hip",
        "name_zh": "上臀围",
        "unit": "cm",
        "description": "Circumference between waist and hip.",
        "description_zh": "腰围与臀围之间，通常指髂骨嵴位置的围度（肚脐下小腹位置）。"
    },
    "hip_circ": {
        "name": "Hip (Circ)",
        "name_zh": "臀围",
        "unit": "cm",
        "description": "Hip size circumference at the largest part.",
        "description_zh": "臀部最翘处（最大围度）。"
    },
    "hip_width": {
        "name": "Hip (Width)",
        "name_zh": "胯宽",
        "unit": "cm",
        "description": "Width, not circumference.",
        "description_zh": "两胯（大转子）之间的直线宽度（非围度）。"
    },
    "hip_padded": {
        "name": "Hip (Padded)",
        "name_zh": "带垫臀围",
        "unit": "cm",
        "description": "Padded measurement with hip pad.",
        "description_zh": "穿戴臀垫后的测量值。"
    },
    "thigh": {
        "name": "Thigh",
        "name_zh": "大腿围",
        "unit": "cm",
        "description": "Thigh size circumference at the largest part.",
        "description_zh": "大腿根部最粗处的围度。"
    },
    "calf": {
        "name": "Calf",
        "name_zh": "小腿围",
        "unit": "cm",
        "description": "Calf size circumference at the largest part.",
        "description_zh": "小腿肚最粗处的围度。"
    },
    "ankle": {
        "name": "Ankle",
        "name_zh": "脚踝围",
        "unit": "cm",
        "description": "Ankle size circumference at the largest part.",
        "description_zh": "脚踝骨上方最细处的围度。"
    },
    "legs": {
        "name": "Legs",
        "name_zh": "内腿长",
        "unit": "cm",
        "description": "Measure from a book in crotch to sole of feet.",
        "description_zh": "书本夹住大腿根部（档底）到脚底地面的垂直距离（内腿长）。"
    },
    "feet": {
        "name": "Feet",
        "name_zh": "脚长",
        "unit": "cm",
        "description": "Length from heel to big toe end.",
        "description_zh": "脚后跟到脚趾尖的直线长度。"
    }
}

# 参考基准
BODY_FAT_STANDARDS = {
    "us_average_female": 32.0,
    "ideal": 22.0,
    "athletic_min": 15.0,
    "athletic_max": 20.0,
    "disorder_threshold": 10.0
}

IDEAL_BENCHMARKS = {
    "female_model": {
        "bmi": 18.9,
        "whr": 0.70,
        "wcr": 0.60,
        "sth": 0.62
    },
    "male_model": {
        "bmi": 18.8,
        "whr": 0.73,
        "wcr": 0.69,
        "sth": 0.62
    }
}

# 基础指标字段集合（用于权限限制）
LIMITED_METRICS_FIELDS = frozenset({
    "bust",
    "waist",
    "hip_circ",
    "thigh",
    "calf",
    "arm",
    "height",
})


def build_metrics_schema_text(allowed_keys: Optional[Iterable[str]] = None) -> str:
    """构建用于提示文本的指标模式描述。"""
    allowed_set = set(allowed_keys) if allowed_keys else set(METRICS_SCHEMA.keys())
    schema_desc = []
    for key, meta in METRICS_SCHEMA.items():
        if key not in allowed_set:
            continue
        name_zh = meta.get("name_zh", "")
        desc_zh = meta.get("description_zh", "")
        unit = meta.get("unit", "")
        schema_desc.append(f"- {key} ({name_zh}): {desc_zh} 单位:{unit}")
    return "\n".join(schema_desc)


def build_metrics_event_schema(allowed_keys: Optional[Iterable[str]] = None) -> dict:
    """构建用于 LLM 结构化输出的指标事件 schema。"""
    allowed_set = set(allowed_keys) if allowed_keys else set(METRICS_SCHEMA.keys())
    metrics_properties = {
        "measured_at_local": {"type": "string", "description": "测量时间/日期"}
    }
    for key, meta in METRICS_SCHEMA.items():
        if key not in allowed_set:
            continue
        metrics_properties[key] = {
            "type": "number",
            "description": meta.get("description_zh", ""),
        }
    return {
        "type": "object",
        "properties": metrics_properties,
        "required": [],
    }


# --- 预设函数（用于简化调用） ---

def build_metrics_schema_text_full() -> str:
    """构建完整指标模式描述（所有字段）。"""
    return build_metrics_schema_text(None)


def build_metrics_schema_text_limited() -> str:
    """构建受限指标模式描述（仅基础字段）。"""
    return build_metrics_schema_text(LIMITED_METRICS_FIELDS)


def build_metrics_event_schema_full() -> dict:
    """构建完整指标事件 schema（所有字段）。"""
    return build_metrics_event_schema(None)


def build_metrics_event_schema_limited() -> dict:
    """构建受限指标事件 schema（仅基础字段）。"""
    return build_metrics_event_schema(LIMITED_METRICS_FIELDS)


def filter_metrics_event(event: Dict[str, Any], use_limited: bool = False) -> None:
    """
    过滤指标事件，只保留允许的字段（始终保留 measured_at_local）。
    如果 use_limited=True，只保留基础字段；否则不进行过滤。
    """
    if not use_limited:
        return
    keep_keys = LIMITED_METRICS_FIELDS | {"measured_at_local"}
    for key in list(event.keys()):
        if key not in keep_keys:
            event.pop(key, None)
