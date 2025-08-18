"""
意图处理器 - 两阶段LLM意图识别和参数提取

第一阶段：意图识别 - 基于语义理解，不依赖关键词匹配
第二阶段：参数提取 - 针对具体意图提取结构化参数
"""

import json
import os
from typing import Dict, Any, Optional, Tuple
from Module.Common.scripts.common import debug_utils
from ..service_decorators import file_processing_safe


class IntentProcessor:
    """
    意图处理器 - 实现两阶段LLM处理流程
    """

    def __init__(self, llm_service, config_path: str = None):
        """
        初始化意图处理器

        Args:
            llm_service: LLMService实例
            config_path: 意图配置文件路径
        """
        self.llm_service = llm_service

        # 加载意图配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "intent_config.json")

        self.config = self._load_config(config_path)
        self.intents = self.config.get("intents", {})
        self.settings = self.config.get("settings", {})

    @file_processing_safe(
        "意图配置加载失败", return_value={"intents": {}, "settings": {}}
    )
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载意图配置文件"""
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        debug_utils.log_and_print(
            f"✅ 意图配置加载成功: {len(config.get('intents', {}))} 个意图",
            log_level="DEBUG",
        )
        return config

    # ==================== 第一阶段：意图识别 ====================

    def _build_stage1_prompt(self, user_input: str) -> str:
        """构建第一阶段意图识别提示词"""
        intent_names = list(self.intents.keys())

        prompt_parts = [
            "# 任务：",
            "深入理解用户输入的语义，为以下每一个定义的意图类型，分别评估其与用户输入匹配的置信度评分（0-100）。",
            "请关注用户想要达成的根本目标，而不是表面的关键词匹配。",
            "",
            "# 支持的意图类型及其核心目标：",
        ]

        # 添加意图定义
        for intent_name, config in self.intents.items():
            prompt_parts.append(f"## 意图：{intent_name}")
            prompt_parts.append(f"   核心目标：{config['core_goal']}")
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "# 分析与输出要求：",
                "1. 对于以下每一个意图类型，给出其匹配用户输入的置信度评分（0-100）：",
            ]
            + [f"   - {name}" for name in intent_names]
            + [
                "2. 对于可能的其他意图，返回可能的意图名称",
                f"# 用户输入：\n{user_input}",
                "",
            ]
        )

        return "\n".join(prompt_parts)

    def _get_stage1_response_schema(self) -> Dict[str, Any]:
        """获取第一阶段响应结构定义"""
        intent_names = list(self.intents.keys())
        intent_scores_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'意图的置信度评分",
            }
            for name in intent_names
        }

        return {
            "type": "object",
            "properties": {
                "intent_scores": {
                    "type": "object",
                    "properties": intent_scores_properties,
                    "required": intent_names,
                    "description": "每个支持意图的置信度评分（0-100）",
                },
                "other_intent_name": {
                    "type": "string",
                    "description": "对于可能的其他意图，返回可能的意图名称",
                },
            },
            "required": ["intent_scores"],
        }

    def recognize_intent_stage1(self, user_input: str) -> Dict[str, Any]:
        """执行第一阶段意图识别"""
        prompt = self._build_stage1_prompt(user_input)
        print("test-", prompt, "\n")

        debug_utils.log_and_print(
            f"🔍 开始第一阶段意图识别: '{user_input[:50]}'", log_level="DEBUG"
        )

        try:
            # 调用LLMService的路由方法
            result = self.llm_service.router_structured_call(
                prompt=prompt,
                response_schema=self._get_stage1_response_schema(),
                system_instruction="你是智能助手意图识别专家。严格按照提供的JSON模式输出，不要输出额外文本。",
                temperature=self.settings.get("stage1_model_config", {}).get(
                    "temperature", 0.1
                ),
            )
            debug_utils.log_and_print(
                f"✅ 第一阶段完成，评分: {result.get('intent_scores', {})}",
                log_level="DEBUG",
            )
            return result

        except Exception as e:
            debug_utils.log_and_print(
                f"❌ 第一阶段意图识别失败: {e}", log_level="ERROR"
            )
            # 返回错误结果
            return {
                "error": str(e),
                "intent_scores": {name: 0 for name in self.intents.keys()},
                "primary_extracted_content": user_input,
                "reasoning_for_scores": f"处理失败: {e}",
            }

    def determine_primary_intent(
        self, stage1_result: Dict[str, Any], confidence_threshold: int = None
    ) -> Tuple[Optional[str], int]:
        """根据第一阶段结果确定主要意图"""
        if confidence_threshold is None:
            confidence_threshold = self.settings.get("default_confidence_threshold", 60)

        if "error" in stage1_result or "intent_scores" not in stage1_result:
            return "其他", 0

        intent_scores = stage1_result["intent_scores"]

        # 优先选择非"其他"的最高分意图
        primary_intent = None
        max_confidence = -1

        for intent, confidence in intent_scores.items():
            if intent == "其他":
                continue
            if confidence > max_confidence:
                max_confidence = confidence
                primary_intent = intent

        # 如果最高分的非"其他"意图超过阈值
        if primary_intent and max_confidence >= confidence_threshold:
            return primary_intent, max_confidence

        # 否则，检查"其他"意图的得分
        other_confidence = intent_scores.get("其他", 0)
        if other_confidence >= confidence_threshold:
            return "其他", other_confidence

        # 如果所有意图都低于阈值，返回得分最高的
        if primary_intent and max_confidence > other_confidence:
            return primary_intent, max_confidence

        return "其他", other_confidence

    # ==================== 第二阶段：参数提取 ====================

    def _build_stage2_prompt(
        self, user_input: str, determined_intent: str
    ) -> Optional[str]:
        """构建第二阶段参数提取提示词"""
        if determined_intent not in self.intents:
            return None

        intent_config = self.intents[determined_intent]
        schema_desc = json.dumps(
            intent_config["stage2_parameters"], indent=2, ensure_ascii=False
        )

        prompt_parts = [
            "# 任务：",
            f"根据已识别的用户意图 {determined_intent}，从以下用户输入中提取相关的参数信息。",
            "如果某些schema中定义的参数在用户输入中未提及，则省略该参数或将其值设为null，考虑一定的用户描述不精确的情况，允许一定程度的模糊匹配。",
            "",
            f"# 用户输入：\n{user_input}",
        ]

        return "\n".join(prompt_parts)

    def extract_parameters_stage2(
        self, user_input: str, determined_intent: str
    ) -> Dict[str, Any]:
        """执行第二阶段参数提取"""
        if determined_intent == "其他" or determined_intent is None:
            # 对于"其他"意图，返回原始输入
            return {
                "parameters": {
                    "original_input": user_input,
                    "possible_category": "未分类",
                }
            }

        if determined_intent not in self.intents:
            return {"error": f"未知意图类型: {determined_intent}"}

        prompt = self._build_stage2_prompt(user_input, determined_intent)
        print("test-prompt_stage2", prompt, "\n")
        if not prompt:
            return {"error": f"无法为意图 {determined_intent} 构建参数提取提示词"}

        debug_utils.log_and_print(
            f"🔧 开始第二阶段参数提取: {determined_intent}", log_level="DEBUG"
        )

        try:
            # 调用LLMService的路由方法
            result = self.llm_service.router_structured_call(
                prompt=prompt,
                response_schema=self.intents[determined_intent]["stage2_parameters"],
                system_instruction="你是参数提取专家。严格按照提供的JSON模式输出，不要输出额外文本。",
                temperature=self.settings.get("stage2_model_config", {}).get(
                    "temperature", 0.2
                ),
            )

            debug_utils.log_and_print(
                f"✅ 第二阶段完成，参数: {list(result.keys())}", log_level="DEBUG"
            )
            return {"parameters": result}

        except Exception as e:
            debug_utils.log_and_print(
                f"❌ 第二阶段参数提取失败: {e}", log_level="ERROR"
            )
            # 返回错误结果
            return {"error": str(e), "parameters": {"original_input": user_input}}

    # ==================== 完整处理流程 ====================

    def process_input(
        self, user_input: str, confidence_threshold: int = None
    ) -> Dict[str, Any]:
        """完整的两阶段意图处理流程"""
        debug_utils.log_and_print(
            f"🚀 开始两阶段意图处理: '{user_input[:50]}...'", log_level="INFO"
        )

        # 第一阶段：意图识别
        stage1_result = self.recognize_intent_stage1(user_input)
        if "error" in stage1_result:
            return {
                "success": False,
                "error": stage1_result["error"],
                "user_input": user_input,
            }

        # 确定主要意图
        primary_intent, intent_confidence = self.determine_primary_intent(
            stage1_result, confidence_threshold
        )

        final_result = {
            "success": True,
            "user_input": user_input,
            "stage1_intent_scores": stage1_result.get("intent_scores"),
            "other_intent_name": stage1_result.get("other_intent_name"),
            "determined_intent": primary_intent,
            "intent_confidence": intent_confidence,
            "parameters": {},
        }

        # 第二阶段：参数提取
        stage2_result = self.extract_parameters_stage2(user_input, primary_intent)
        if "error" in stage2_result:
            final_result["parameter_extraction_error"] = stage2_result["error"]
            final_result["parameters"] = stage2_result.get(
                "parameters", {"original_input": user_input}
            )
        else:
            final_result["parameters"] = stage2_result.get("parameters", {})

        debug_utils.log_and_print(
            f"🎯 意图处理完成: {primary_intent} (置信度: {intent_confidence})",
            log_level="INFO",
        )
        debug_utils.log_and_print(
            f"🎯 意图处理明细: \n{final_result}", log_level="INFO"
        )

        return final_result

    def get_supported_intents(self) -> Dict[str, str]:
        """获取支持的意图列表"""
        return {name: config["description"] for name, config in self.intents.items()}

    def get_status(self) -> Dict[str, Any]:
        """获取处理器状态"""
        return {
            "processor_name": "IntentProcessor",
            "model_name": self.llm_service.model_name if self.llm_service else None,
            "groq_available": (
                hasattr(self.llm_service, "groq_client")
                and self.llm_service.groq_client is not None
                if self.llm_service
                else False
            ),
            "supported_intents": list(self.intents.keys()),
            "intent_count": len(self.intents),
            "confidence_threshold": self.settings.get(
                "default_confidence_threshold", 60
            ),
            "config_loaded": bool(self.intents),
        }
