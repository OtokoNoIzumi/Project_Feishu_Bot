"""
LLM服务 - 基于Google Gemini的大语言模型服务

提供两阶段意图识别和参数提取功能
"""

import os
import json
from typing import Dict, Any
from google import genai
from google.genai import types
from Module.Common.scripts.common import debug_utils
from .intent_processor import IntentProcessor


class LLMService:
    """
    LLM服务 - 封装Gemini API调用和意图处理
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
        self.intent_processor = None

        # 初始化配置
        self._init_config()

        # 创建Gemini客户端
        self._init_client()

        # 初始化意图处理器
        self._init_intent_processor()

    def _init_config(self):
        """初始化配置（简洁版）"""
        default_model = 'gemini-2.5-flash-preview-05-20'
        try:
            config_service = None
            if self.app_controller:
                config_service = self.app_controller.get_service('config')

            if config_service:
                self.model_name = config_service.get('GEMINI_MODEL_NAME', default_model)
                self.api_key = config_service.get_env('GEMINI_API_KEY')
                log_level = "DEBUG"
                msg = "📋 LLM配置加载成功"
            else:
                self.model_name = default_model
                self.api_key = os.getenv('GEMINI_API_KEY')
                msg = "⚠️ 配置服务不可用，使用默认配置" if self.app_controller else "⚠️ 无应用控制器，使用默认配置"
                log_level = "WARNING"

            debug_utils.log_and_print(
                f"{msg}: 模型={self.model_name}, API密钥={'已设置' if self.api_key else '未设置'}",
                log_level=log_level
            )
        except Exception as e:
            debug_utils.log_and_print(f"❌ LLM配置初始化失败: {e}", log_level="ERROR")
            self.model_name = default_model
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

    def _init_intent_processor(self):
        """初始化意图处理器"""
        try:
            if self.client and self.model_name:
                self.intent_processor = IntentProcessor(
                    llm_client=self.client,
                    model_name=self.model_name
                )
                debug_utils.log_and_print("✅ 意图处理器初始化成功", log_level="DEBUG")
            else:
                debug_utils.log_and_print("⚠️ 无法初始化意图处理器：LLM客户端不可用", log_level="WARNING")
                self.intent_processor = None
        except Exception as e:
            debug_utils.log_and_print(f"❌ 意图处理器初始化失败: {e}", log_level="ERROR")
            self.intent_processor = None

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self.client is not None and self.intent_processor is not None

    def process_input_advanced(self, user_input: str, confidence_threshold: int = None) -> Dict[str, Any]:
        """
        高级意图处理接口（完整的两阶段结果）

        Args:
            user_input: 用户输入内容
            confidence_threshold: 置信度阈值

        Returns:
            Dict[str, Any]: 完整的处理结果
        """
        if not self.is_available():
            return {
                'success': False,
                'error': 'LLM服务不可用'
            }

        return self.intent_processor.process_input(user_input, confidence_threshold)

    def get_supported_intents(self) -> Dict[str, str]:
        """获取支持的意图列表"""
        if self.intent_processor:
            return self.intent_processor.get_supported_intents()
        return {}

    def simple_chat(self, prompt: str, max_tokens: int = 1500) -> str:
        """
        简单的聊天接口，用于通用文本生成

        Args:
            prompt: 输入的提示词
            max_tokens: 最大生成token数

        Returns:
            str: 生成的文本内容
        """
        if not self.client:
            return "LLM客户端不可用"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{
                    'role': 'user',
                    'parts': [{'text': prompt}]
                }],
                config={
                    "thinking_config": types.ThinkingConfig(
                        thinking_budget=-1,
                    ),
                    'temperature': 0.7,
                    'max_output_tokens': max_tokens
                }
            )
            return response.text
        except Exception as e:
            debug_utils.log_and_print(f"❌ simple_chat 调用失败: {e}", log_level="ERROR")
            return f"文本生成失败: {e}"

    def structured_call(self,
                       prompt: str,
                       response_schema: Dict[str, Any],
                       system_instruction: str = None,
                       temperature: float = 0.95,
                       thinking_budget: int = 0) -> Dict[str, Any]:
        """
        结构化调用接口，支持JSON schema和系统提示词

        Args:
            prompt: 用户提示词
            response_schema: JSON响应schema
            system_instruction: 系统提示词
            temperature: 温度参数
            thinking_budget: 思考预算

        Returns:
            Dict[str, Any]: 结构化响应结果
        """
        if not self.client:
            return {"error": "LLM客户端不可用"}

        try:
            # 构建请求内容
            contents = [{
                'role': 'user',
                'parts': [{'text': prompt}]
            }]

            # 构建配置
            config = {
                'response_mime_type': 'application/json',
                'response_schema': response_schema,
                'thinking_config': types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                ),
                'temperature': temperature
            }

            # 如果有系统提示词，添加到配置中
            if system_instruction:
                config['system_instruction'] = system_instruction

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )

            # 尝试解析JSON响应
            return json.loads(response.text)

        except json.JSONDecodeError as e:
            debug_utils.log_and_print(f"❌ JSON解析失败: {e}, 响应内容: {response.text[:200] if 'response' in locals() else 'None'}", log_level="ERROR")
            return {"error": f"JSON解析失败: {e}"}
        except Exception as e:
            debug_utils.log_and_print(f"❌ structured_call 调用失败: {e}", log_level="ERROR")
            return {"error": f"结构化调用失败: {e}"}

    def get_status(self) -> Dict[str, Any]:
        """获取LLM服务状态"""
        status = {
            "service_name": "LLMService",
            "model_name": self.model_name,
            "available": self.is_available(),
            "api_key_configured": bool(self.api_key),
            "client_initialized": self.client is not None,
            "intent_processor_initialized": self.intent_processor is not None
        }

        if self.intent_processor:
            processor_status = self.intent_processor.get_status()
            status.update({
                "supported_intents": processor_status.get("supported_intents", []),
                "intent_count": processor_status.get("intent_count", 0),
                "confidence_threshold": processor_status.get("confidence_threshold", 60)
            })

        return status