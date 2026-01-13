"""
Weekly Analysis LLM Schema.

Gemini-compatible JSON schema for weekly analysis output.
Uses manual dict definition (not Pydantic auto-generated) to avoid
'additionalProperties' which Gemini doesn't support.

V2: 引入"侦探思维"，增加交叉分析和深度洞察字段
"""

from typing import Dict


# --- Executive Summary Schema ---
EXECUTIVE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "像新闻标题一样吸引人，如'水肿警报：周末高盐晚餐的代价'或'稳中有进：蛋白质摄入达标周'",
        },
        "summary": {
            "type": "string",
            "description": "100字以内的综述，串联饮食与身体变化的因果关系，点出关键发现",
        },
    },
    "required": ["title", "summary"],
}


# --- Dish Evaluation Schema ---
DISH_EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
        "meal_type": {"type": "string", "description": "breakfast/lunch/dinner/snack"},
        "dish_name": {"type": "string", "description": "单个菜品名称，如'干蒸牛肉'"},
        "score": {"type": "integer", "description": "健康评分1-10"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "情绪化标签，如'减脂神器'、'高蛋白炸弹'、'控糖优选'、'钠盐炸弹'、'碳水陷阱'",
        },
        "why_good_or_bad": {
            "type": "string",
            "description": "为什么这道菜值得表扬或需要改进，50字内",
        },
    },
    "required": ["date", "meal_type", "dish_name", "score", "tags", "why_good_or_bad"],
}


# --- Deep Dive Analysis Schema (替换原Diet Analysis) ---
DEEP_DIVE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer", "description": "周饮食整体评分0-100"},
        "truth_about_weight": {
            "type": "string",
            "description": "分析体重变化的'质量'。是脱水？掉肌肉？还是真的减脂？结合饮食成分(蛋白/钠)和水分率分析。100-150字。",
        },
        "highlight_moment": {
            "type": "string",
            "description": "本周做得最棒的一个具体行为或一顿饭，给予高度肯定，解释为什么这很重要。80字内。",
        },
        "sabotage_event": {
            "type": "string",
            "description": "破坏本周成果的关键事件（如周日的水煮鱼），解释它造成的后果。如果没有明显破坏事件则说'本周无重大失误'。80字内。",
        },
        "top_dishes": {
            "type": "array",
            "items": DISH_EVALUATION_SCHEMA,
            "description": "本周最佳菜品（最多3个单独菜品）",
        },
        "problem_dishes": {
            "type": "array",
            "items": DISH_EVALUATION_SCHEMA,
            "description": "需改进菜品（最多3个单独菜品，高钠/高脂等）",
        },
    },
    "required": [
        "overall_score",
        "truth_about_weight",
        "highlight_moment",
        "sabotage_event",
        "top_dishes",
        "problem_dishes",
    ],
}


# --- Body Composition Trends Schema ---
BODY_COMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "water_retention_status": {
            "type": "string",
            "enum": ["normal", "mild_edema", "severe_edema"],
            "description": "水肿状态：normal正常 / mild_edema轻度水肿 / severe_edema明显水肿，基于钠摄入和体重波动判断",
        },
        "water_retention_reason": {
            "type": "string",
            "description": "水肿原因分析，如'周末钠摄入超3000mg导致水分滞留'。50字内。",
        },
        "muscle_maintenance": {
            "type": "string",
            "description": "肌肉保持评价：基于蛋白质摄入量和骨骼肌数据，判断是否在掉肌肉。60字内。",
        },
        "visceral_fat_trend": {
            "type": "string",
            "description": "内脏脂肪趋势评价，结合腰围变化分析。40字内。",
        },
    },
    "required": [
        "water_retention_status",
        "water_retention_reason",
        "muscle_maintenance",
        "visceral_fat_trend",
    ],
}


# --- Key Insight Schema ---
KEY_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "phenomenon": {
            "type": "string",
            "description": "观察到的现象，如'体重降0.8kg但腰围反增1cm'",
        },
        "data_evidence": {
            "type": "string",
            "description": "支持这个结论的数据证据，引用具体数值",
        },
        "root_cause": {
            "type": "string",
            "description": "根本原因推断",
        },
        "actionable_advice": {
            "type": "string",
            "description": "可立即执行的建议，如'明早空腹喝黑咖啡利尿'",
        },
    },
    "required": ["phenomenon", "data_evidence", "root_cause", "actionable_advice"],
}


# --- Meal Suggestion Schema ---
MEAL_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "target_dish": {
            "type": "string",
            "description": "建议替换的菜品，如'水煮鱼'",
        },
        "suggested_alternative": {
            "type": "string",
            "description": "建议的替代，如'清蒸鲈鱼'",
        },
        "reason": {"type": "string", "description": "替换理由，40字内"},
    },
    "required": ["target_dish", "suggested_alternative", "reason"],
}


# --- Next Week Strategy Schema ---
NEXT_WEEK_STRATEGY_SCHEMA = {
    "type": "object",
    "properties": {
        "weekly_challenge": {
            "type": "string",
            "description": "下周挑战目标，游戏化表述，如'挑战将晚餐钠控制在1500mg内，消除腰部水肿'",
        },
        "one_thing_to_fix": {
            "type": "string",
            "description": "只提一个最重要、最容易执行的改变",
        },
        "meal_swaps": {
            "type": "array",
            "items": MEAL_SUGGESTION_SCHEMA,
            "description": "餐食替换建议（最多3条）",
        },
    },
    "required": ["weekly_challenge", "one_thing_to_fix", "meal_swaps"],
}


# --- Dimension Change Schema ---
DIMENSION_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "waist_change_cm": {"type": "number", "description": "腰围变化(cm)"},
        "waist_hip_ratio": {"type": "number", "description": "当前腰臀比，无数据则为0"},
        "interpretation": {
            "type": "string",
            "description": "围度变化解读，结合体重和钠摄入分析原因。80字内。",
        },
    },
    "required": ["waist_change_cm", "waist_hip_ratio", "interpretation"],
}


# --- Main Weekly Analysis Schema V2 ---
WEEKLY_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": EXECUTIVE_SUMMARY_SCHEMA,
        "week_range": {
            "type": "string",
            "description": "分析周期，如'2026-01-06 至 2026-01-12'",
        },
        "key_insight": KEY_INSIGHT_SCHEMA,
        "deep_dive_analysis": DEEP_DIVE_ANALYSIS_SCHEMA,
        "body_composition": BODY_COMPOSITION_SCHEMA,
        "dimension_change": DIMENSION_CHANGE_SCHEMA,
        "next_week_strategy": NEXT_WEEK_STRATEGY_SCHEMA,
    },
    "required": [
        "executive_summary",
        "week_range",
        "key_insight",
        "deep_dive_analysis",
        "body_composition",
        "next_week_strategy",
    ],
}


def get_weekly_analysis_schema() -> Dict:
    """
    Return the Gemini-compatible JSON schema for weekly analysis.
    """
    return WEEKLY_ANALYSIS_SCHEMA
