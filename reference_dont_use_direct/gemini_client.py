"""
Gemini API接口封装 - 提供对Google Gemini API的访问功能
"""

import os
from google import genai

# 从analyzer.py移动过来的响应模式定义
response_schema = {
    "type": "object",
    "properties": {
        "a_recommendation_reason": {"type": "string", "description": "推荐观看这个视频的最大理由"},
        "category_confidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["category", "confidence"]
            },
            "description": "每个分组类别的置信度评分（0-100）"
        },
        "negative_category_confidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["category", "confidence"]
            },
            "description": "负面分类类别的置信度评分（0-100），'推广广告'表示整个视频主要目的是商业推广"
        },
        "ad_timestamps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_time": {"type": "number", "description": "广告开始时间（秒）"},
                    "end_time": {"type": "number", "description": "广告结束时间（秒）"},
                    "description": {"type": "string", "description": "广告内容简要描述"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["start_time", "end_time", "confidence"]
            },
            "description": "视频中植入广告的时间戳和描述，这些是在有实质内容的视频中插入的广告片段"
        },
        "component_ad_confidence": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "标题的推广广告倾向性评分"
                },
                "desc_dynamic": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "投稿说明和作者动态的推广广告倾向性评分"
                },
                "subtitle": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "字幕内容的推广广告倾向性评分"
                }
            },
            "required": ["title", "desc_dynamic", "subtitle"],
            "description": "各个视频信息组件的推广广告倾向性评分，如果对应内容不存在，则倾向性数值为0"
        },
        "time_relevance": {
            "type": "object",
            "properties": {
                "time_sensitive_coefficient": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "内容具有时效性（如新闻、天气、热点事件等）的置信度"
                },
                "value_coefficient": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "当前信息价值系数（0表示完全过时无价值，100表示价值完全保留）"
                },
                "time_sensitive_summary": {
                    "type": "string",
                    "description": "时效性内容摘要"
                }
            },
            "required": [
                "time_sensitive_coefficient",
                "value_coefficient",
                "time_sensitive_summary"
            ],
            "description": "视频内容的时效性评估"
        }
    },
    "required": [
        "a_recommendation_reason",
        "category_confidence",
        "component_ad_confidence",
        "time_relevance"
    ]
}


def create_gemini_client(api_key=None):
    """
    创建Gemini API客户端

    参数:
    - api_key: Gemini API密钥，默认从环境变量获取

    返回:
    - Gemini客户端实例
    """
    if api_key is None:
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("未提供Gemini API密钥，请设置 GEMINI_API_KEY 环境变量或直接传入api_key参数")

    return genai.Client(api_key=api_key)


def get_default_model_name():
    """
    获取默认使用的Gemini模型名称

    返回:
    - 默认模型名称字符串
    """
    return "gemini-2.5-flash"
    # return "gemini-2.0-flash"


def get_system_prompt():
    """
    获取默认的系统提示词

    返回:
    - 系统提示词字符串
    """
    return """
# Role: 影视飓风创始人Tim
# Background: 你是影视飓风创始人Tim，拥有顶尖视觉媒体专业素养和一批严谨的科学专家顾问团队。你的任务是基于视频附属信息分析内容，提供准确分类和亮点。
# Profile: 你以客观专业的视角评估视频，不受制作者自述和AI概要影响，而是基于实际内容给出判断。
# Skills: 视频内容分析、科学信息鉴别、观点与证据匹配度评估、营销内容识别。
# Goals: 提供准确的视频分类和推荐亮点，帮助用户筛选优质内容。
# Constrains: 保持客观谨慎，不轻信稿件说法，基于事实评估。
# OutputFormat: 结构化分析报告，包含分类置信度和推荐理由。
# Workflow:
  1. 基于提供的视频标题、概要，可能提供的AI摘要和字幕，判断视频属于哪些分类及其置信度
  2. 识别视频中的价值点和潜在问题
  3. 警惕并标记出伪科学、虚假健康信息、夸大功效等误导性内容和推广广告等商业利益驱动的内容，尤其警惕基于中医的未经验证结论及养生建议（你我均不认可）
  4. 对于提出了主张或观点，而不是谈论个人感受的情况，请判断主张是否基于事实，以及主张和证据之间的匹配程度
  5. 区分有观赏价值的广告内容，不带营销立场的教育、科普内容，以及各类营销内容
  6. 明确区分"推广广告"和"植入广告"：
     - 推广广告：整个视频的主要目的是商业推广，内容重点是推销产品或服务
     - 植入广告：在有实质内容的视频中插入的广告片段，这种情况下视频本身不应被归类为广告，但需要标注出广告片段的时间戳
"""


def get_field_keys():
    """
    获取字段分类定义

    返回:
    - 字段分类定义字典
    """
    return {
        'AI': '人工智能、机器学习、深度学习等相关技术内容',
        '健身': '健身教程、运动技巧、肌肉训练、康复训练、身体塑形等内容',
        '健康': '健康知识、医学科普、营养学等身体健康相关内容',
        '学习': '学术知识、技能培训、教育内容，但不包括游戏攻略、动画观感等娱乐内容',
        '生活': '不限于日常生活技巧、居家装修、烹饪美食、生活方式、天气信息等相关内容，但并不是以娱乐放松为目的，而是提供信息'
    }


def get_negative_field_keys():
    """
    获取负面类型定义

    返回:
    - 负面类型列表
    """
    return ["推广广告", "伪科学", "中医养生建议"]
