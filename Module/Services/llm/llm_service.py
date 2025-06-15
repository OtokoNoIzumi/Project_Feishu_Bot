"""
LLM服务 - 基于Google Gemini的大语言模型服务

提供意图识别、内容分析等功能
基于参考文件gemini_client.py和prompt_builder.py的架构
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from google import genai
from Module.Common.scripts.common import debug_utils


class LLMService:
    """
    LLM服务 - 封装Gemini API调用和提示词管理
    """

    def __init__(self, app_controller=None):
        """
        初始化LLM服务

        Args:
            app_controller: 应用控制器，用于获取配置
        """
        self.app_controller = app_controller
        self.client = None
        self.model_name = None
        self.api_key = None

        # 初始化配置
        self._init_config()

        # 创建Gemini客户端
        self._init_client()

    def _init_config(self):
        """初始化配置"""
        try:
            if self.app_controller:
                config_service = self.app_controller.get_service('config')
                if config_service:
                    # 从配置获取模型名称
                    self.model_name = config_service.get('GEMINI_MODEL_NAME', 'gemini-2.5-flash-preview-05-20')
                    # API密钥从环境变量获取
                    self.api_key = config_service.get_env('GEMINI_API_KEY')
                    debug_utils.log_and_print(f"📋 LLM配置加载成功: 模型={self.model_name}, API密钥={'已设置' if self.api_key else '未设置'}", log_level="DEBUG")
                else:
                    # 配置服务不可用时的fallback
                    self.model_name = 'gemini-2.5-flash-preview-05-20'
                    self.api_key = os.getenv('GEMINI_API_KEY')
                    debug_utils.log_and_print(f"⚠️ 配置服务不可用，使用默认配置: 模型={self.model_name}, API密钥={'已设置' if self.api_key else '未设置'}", log_level="WARNING")
            else:
                # 默认配置
                self.model_name = 'gemini-2.5-flash-preview-05-20'
                self.api_key = os.getenv('GEMINI_API_KEY')
                debug_utils.log_and_print(f"⚠️ 无应用控制器，使用默认配置: 模型={self.model_name}, API密钥={'已设置' if self.api_key else '未设置'}", log_level="WARNING")
        except Exception as e:
            debug_utils.log_and_print(f"❌ LLM配置初始化失败: {e}", log_level="ERROR")
            # 使用默认配置作为fallback
            self.model_name = 'gemini-2.5-flash-preview-05-20'
            self.api_key = os.getenv('GEMINI_API_KEY')

    def _init_client(self):
        """初始化Gemini客户端"""
        try:
            if not self.api_key:
                raise ValueError("未提供Gemini API密钥，请设置 GEMINI_API_KEY 环境变量")

            self.client = genai.Client(api_key=self.api_key)
            debug_utils.log_and_print(f"✅ LLM服务初始化成功，模型: {self.model_name}", log_level="INFO")

        except Exception as e:
            debug_utils.log_and_print(f"❌ LLM服务初始化失败: {e}", log_level="ERROR")
            self.client = None

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self.client is not None

    def identify_intent(self, user_input: str, user_id: str) -> Dict[str, Any]:
        """
        识别用户意图

        Args:
            user_input: 用户输入内容
            user_id: 用户ID（用于个性化）

        Returns:
            Dict[str, Any]: 意图识别结果
        """
        if not self.is_available():
            return {
                'success': False,
                'error': 'LLM服务不可用',
                'intent': 'unknown',
                'confidence': 0
            }

        try:
            # 构建意图识别提示词
            prompt = self._build_intent_prompt(user_input, user_id)

            # 定义响应结构
            response_schema = self._get_intent_response_schema()

            # 调用Gemini API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{
                    'role': 'user',
                    'parts': [{'text': prompt}]
                }],
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': response_schema
                }
            )

            # 解析响应
            result = json.loads(response.text)
            result['success'] = True

            debug_utils.log_and_print(f"🎯 意图识别完成: {result.get('intent', 'unknown')} (置信度: {result.get('confidence', 0)})", log_level="INFO")

            return result

        except Exception as e:
            debug_utils.log_and_print(f"❌ 意图识别失败: {e}", log_level="ERROR")
            return {
                'success': False,
                'error': str(e),
                'intent': 'unknown',
                'confidence': 0
            }

    def _build_intent_prompt(self, user_input: str, user_id: str) -> str:
        """
        构建意图识别提示词

        Args:
            user_input: 用户输入
            user_id: 用户ID

        Returns:
            str: 完整的提示词
        """
        # 获取支持的意图类型和参数
        intent_configs = self._get_intent_configs()

        prompt_parts = [
            "# 角色：智能助手意图识别专家",
            "",
            "# 任务：分析用户输入，识别最可能的意图类型并提供相关参数",
            "",
            "# 支持的意图类型：",
        ]

        # 添加意图类型描述
        for intent_type, config in intent_configs.items():
            prompt_parts.append(f"## {intent_type}")
            prompt_parts.append(f"描述：{config['description']}")
            prompt_parts.append(f"关键词：{', '.join(config['keywords'])}")
            prompt_parts.append("")

        prompt_parts.extend([
            "# 分析要求：",
            "1. 基于用户输入内容，判断最可能的意图类型",
            "2. 给出0-100的置信度评分",
            "3. 如果置信度低于60，标记为'其他'意图",
            "4. 提取相关的参数信息用于后续处理",
            "",
            f"# 用户输入：{user_input}",
            "",
            "请分析上述输入并返回结构化结果。"
        ])

        return "\n".join(prompt_parts)

    def _get_intent_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        获取意图配置

        Returns:
            Dict[str, Dict[str, Any]]: 意图配置字典
        """
        return {
            "记录思考": {
                "description": "用户想要记录想法、思考、感悟等内容",
                "keywords": ["记录", "想法", "思考", "感悟", "笔记", "今天", "刚才", "想到"],
                "parameters": {
                    "content": "要记录的具体内容",
                    "suggested_tags": "建议的标签列表",
                    "confidence_scores": "各标签的置信度"
                }
            },
            "记录日程": {
                "description": "用户想要记录日程安排、任务、事件等",
                "keywords": ["日程", "安排", "任务", "会议", "约会", "提醒", "明天", "下周"],
                "parameters": {
                    "event_content": "日程具体内容",
                    "time_info": "时间相关信息",
                    "status": "事件状态（计划/进行中/完成）"
                }
            },
            "点餐": {
                "description": "用户想要点餐或询问餐饮相关信息",
                "keywords": ["点餐", "外卖", "吃", "饿了", "菜单", "餐厅", "美食"],
                "parameters": {
                    "food_type": "食物类型",
                    "preferences": "偏好信息"
                }
            },
            "其他": {
                "description": "无法明确分类的其他意图",
                "keywords": [],
                "parameters": {}
            }
        }

    def _get_intent_response_schema(self) -> Dict[str, Any]:
        """
        获取意图识别响应结构定义

        Returns:
            Dict[str, Any]: JSON Schema定义
        """
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "识别出的意图类型",
                    "enum": ["记录思考", "记录日程", "点餐", "其他"]
                },
                "confidence": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "意图识别的置信度（0-100）"
                },
                "extracted_content": {
                    "type": "string",
                    "description": "从用户输入中提取的核心内容"
                },
                "parameters": {
                    "type": "object",
                    "description": "根据意图类型提取的相关参数",
                    "properties": {
                        "suggested_tags": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tag": {"type": "string"},
                                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                                }
                            },
                            "description": "建议的标签及置信度（仅记录思考时使用）"
                        },
                        "time_info": {
                            "type": "object",
                            "properties": {
                                "mentioned_time": {"type": "string"},
                                "is_future": {"type": "boolean"},
                                "urgency": {"type": "integer", "minimum": 0, "maximum": 100}
                            },
                            "description": "时间相关信息（仅记录日程时使用）"
                        },
                        "food_preferences": {
                            "type": "object",
                            "properties": {
                                "cuisine_type": {"type": "string"},
                                "dietary_restrictions": {"type": "array", "items": {"type": "string"}}
                            },
                            "description": "饮食偏好信息（仅点餐时使用）"
                        }
                    }
                },
                "reasoning": {
                    "type": "string",
                    "description": "意图识别的推理过程说明"
                }
            },
            "required": ["intent", "confidence", "extracted_content", "parameters", "reasoning"]
        }

    def get_status(self) -> Dict[str, Any]:
        """获取LLM服务状态"""
        return {
            "service_name": "LLMService",
            "model_name": self.model_name,
            "available": self.is_available(),
            "api_key_configured": bool(self.api_key),
            "supported_intents": list(self._get_intent_configs().keys())
        }