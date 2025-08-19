"""
意图处理器 - 两阶段LLM意图识别和参数提取

第一阶段：意图识别 - 基于语义理解，不依赖关键词匹配
第二阶段：参数提取 - 针对具体意图提取结构化参数
"""

import json
import os
from typing import Dict, Any, Optional, Tuple, List
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

    # region 一阶段功能识别

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

    # endregion

    # region 二阶段参数提取

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

    # endregion

    # region router调用入口

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

    # endregion

    # region STT调用入口

    def process_stt_input(self, user_input: str) -> List[Dict[str, Any]]:
        """处理STT输入 - 返回前2个角色的流式回复生成器

        Args:
            user_input: 用户输入的文本

        Returns:
            List[Dict[str, Any]]: 包含role_name、confidence、stream_completion三个字段的角色列表
        """
        debug_utils.log_and_print(
            f"🎤 开始处理STT输入: '{user_input[:50]}...'", log_level="INFO"
        )

        # 获取角色路由结果（前2个角色）
        picked_roles = self.role_router(user_input)

        # 为每个角色组装流式回复生成器
        for role in picked_roles:
            role_name = role["role_name"]

            # 从STT_ROLE_DICT获取系统提示词
            role_system_prompt = self.STT_ROLE_DICT[role_name]["system_prompt"]
            final_prompt = f"# 用户输入：\n{user_input}"

            # 使用Gemini获取流式回复生成器
            stream_completion = self.llm_service.get_stream_completion(
                final_prompt, role_system_prompt
            )

            role["stream_completion"] = stream_completion

        return picked_roles

    STT_ROLE_DICT = {
        "思辨自我": {
            "thinking_mode": "概念构建",
            "core_goal": "用户正在构建、定义或澄清概念，进行抽象思考和理论框架构建",
            "typical_patterns": ["提出新概念", "重新定义", "抽象化思考"],
            "response_strategy": "先肯定概念的价值，然后从一个新角度丰富这个概念",
            "system_prompt": "你是用户的思辨自我，擅长概念构建和理论思考。用温暖而深刻的语调，先确认用户概念的价值，再从新角度丰富这个概念。回应长度50-150字，语调自然有温度。",
        },
        "探索伙伴": {
            "thinking_mode": "问题探索",
            "core_goal": "用户正在探索问题本质、寻找答案或深入理解现象",
            "typical_patterns": ["疑问句", "探索性思考", "为什么/如何类思考"],
            "response_strategy": "顺着用户的探索思路，提出能推进思考的问题",
            "system_prompt": "你是探索伙伴，善于引导深入思考。跟随用户的探索方向，提出能推进思考的深化问题。用好奇而支持的语调，先呼应再增强。回应长度50-150字。",
        },
        "智慧镜子": {
            "thinking_mode": "经验总结",
            "core_goal": "用户在回顾、反思、总结已有经验或观察现象",
            "typical_patterns": ["我发现", "感觉", "经验性描述"],
            "response_strategy": "肯定经验，并帮助发现其中的普遍性规律",
            "system_prompt": "你是智慧镜子，擅长从经验中提炼智慧。确认用户经验的价值，帮助发现其中的普遍性规律。用理解而升华的语调回应。回应长度50-150字。",
        },
        "灵感催化师": {
            "thinking_mode": "灵感闪现",
            "core_goal": "突然的想法、创意火花、灵光一现式的思考片段",
            "typical_patterns": ["跳跃性思考", "突然的连接", "突然想到"],
            "response_strategy": "捕捉灵感的核心，并给出可能的延伸路径",
            "system_prompt": "你是灵感催化师，善于放大创意火花。捕捉用户灵感的核心亮点，给出可能的延伸发展路径。用兴奋而启发的语调回应。回应长度50-150字。",
        },
        "情感链接者": {
            "thinking_mode": "情景描述",
            "core_goal": "描述具体情况、场景或事件，可能带有情感色彩",
            "typical_patterns": ["叙述性内容", "情况描述", "场景重现"],
            "response_strategy": "与情景产生共鸣，并发现其中的深层含义",
            "system_prompt": "你是情感链接者，善于情景共鸣。与用户的情景产生共鸣，发现其中的深层含义和情感价值。用共情而洞察的语调回应。回应长度50-150字。",
        },
        "认知导师": {
            "thinking_mode": "元思考",
            "core_goal": "对思考本身的思考，对认知过程的反思",
            "typical_patterns": ["思考方法", "认知模式", "思维过程讨论"],
            "response_strategy": "反映用户的思维过程，并在认知层面给出回应",
            "system_prompt": "你是认知导师，专注于思维过程本身。映射用户的思维过程，在认知层面提供反思和回应。用睿智而引导的语调回应。回应长度50-150字。",
        },
        "想法孵化器": {
            "thinking_mode": "模糊表达",
            "core_goal": "想法尚未成形，表达较为模糊或片段化",
            "typical_patterns": ["不完整句子", "模糊感受", "未明确想法"],
            "response_strategy": "帮助模糊想法找到表达形式和发展方向",
            "system_prompt": "你是想法孵化器，善于理解模糊意图。帮助用户的模糊想法找到表达形式和发展方向，提供成形的思考框架。用耐心而启发的语调回应。回应长度50-150字。",
        },
    }

    def _build_role_identification_prompt(self, user_input: str) -> str:
        """构建角色识别提示词，基于STT_ROLE_DICT"""
        prompt_parts = [
            "# 任务：",
            "深入理解用户输入的思维模式，为以下每一个思维角色，分别评估其与用户输入匹配的置信度评分（0-100）。",
            "请关注用户的思考类型和表达方式，而不是表面的关键词匹配。",
            "",
            "# 思维角色及其特征：",
        ]

        # 添加角色定义
        for role_name, config in self.STT_ROLE_DICT.items():
            prompt_parts.append(f"## 角色：{role_name}")
            prompt_parts.append(f"   思维模式：{config['thinking_mode']}")
            prompt_parts.append(f"   核心目标：{config['core_goal']}")
            prompt_parts.append(f"   典型模式：{', '.join(config['typical_patterns'])}")
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "# 分析与输出要求：",
                "1. 对于以下每一个思维角色，给出其匹配用户输入的置信度评分（0-100）：",
            ]
        )

        # 添加角色名称列表
        for role_name in self.STT_ROLE_DICT.keys():
            prompt_parts.append(f"   - {role_name}")

        prompt_parts.extend(
            [
                "2. 提供简要的推理说明",
                f"# 用户输入：\n{user_input}",
                "",
            ]
        )

        return "\n".join(prompt_parts)

    def _get_role_identification_schema(self) -> Dict[str, Any]:
        """定义角色评分的响应结构"""
        role_names = list(self.STT_ROLE_DICT.keys())
        role_scores_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'角色的置信度评分",
            }
            for name in role_names
        }

        return {
            "type": "object",
            "properties": {
                "role_scores": {
                    "type": "object",
                    "properties": role_scores_properties,
                    "required": role_names,
                    "description": "每个思维角色的置信度评分（0-100）",
                },
                "reasoning": {
                    "type": "string",
                    "description": "对评分结果的简要推理说明",
                },
            },
            "required": ["role_scores"],
        }

    def _identify_role_mode(self, user_input: str) -> Dict[str, int]:
        """第一阶段：识别最匹配的角色模式"""
        prompt = self._build_role_identification_prompt(user_input)
        schema = self._get_role_identification_schema()

        try:
            result = self.llm_service.router_structured_call(
                prompt=prompt,
                response_schema=schema,
                system_instruction="你是思维模式识别专家，能够准确识别用户的思考类型并匹配合适的回应角色。",
                temperature=0.1,
            )

            debug_utils.log_and_print(
                f"✅ STT角色识别完成，评分: {result.get('role_scores', {})}",
                log_level="DEBUG",
            )
            return result.get("role_scores", {})

        except Exception as e:
            debug_utils.log_and_print(f"❌ STT角色识别失败: {e}", log_level="ERROR")
            # 返回默认评分，所有角色得分为0
            return {name: 0 for name in self.STT_ROLE_DICT.keys()}

    def _select_top_roles(
        self, role_scores: Dict[str, int], top_k: int = 2
    ) -> List[Dict[str, Any]]:
        """选择置信度最高的前K个角色

        Args:
            role_scores: 角色评分字典，格式为 {role_name: confidence_score}
            top_k: 选择前K个角色，默认为2

        Returns:
            List[Dict]: 包含role_name和confidence字段的角色列表
        """
        # 处理空输入或异常情况
        if not role_scores or not isinstance(role_scores, dict):
            debug_utils.log_and_print(
                "⚠️ 角色评分为空或格式异常，返回默认角色", log_level="WARNING"
            )
            # 返回默认角色（想法孵化器，适合处理模糊输入）
            return [{"role_name": "想法孵化器", "confidence": 50}]

        # 过滤有效的角色评分
        valid_scores = []
        for role_name, confidence in role_scores.items():
            # 检查角色是否存在于STT_ROLE_DICT中
            if role_name not in self.STT_ROLE_DICT:
                debug_utils.log_and_print(
                    f"⚠️ 角色 '{role_name}' 不存在于STT_ROLE_DICT中，跳过",
                    log_level="WARNING",
                )
                continue

            # 检查置信度是否为有效数值
            try:
                confidence_int = int(confidence)
                # 确保置信度在合理范围内
                confidence_int = max(0, min(100, confidence_int))
                valid_scores.append((role_name, confidence_int))
            except (ValueError, TypeError):
                debug_utils.log_and_print(
                    f"⚠️ 角色 '{role_name}' 的置信度 '{confidence}' 无效，跳过",
                    log_level="WARNING",
                )
                continue

        # 如果没有有效的角色评分，返回默认角色
        if not valid_scores:
            debug_utils.log_and_print(
                "⚠️ 没有有效的角色评分，返回默认角色", log_level="WARNING"
            )
            return [{"role_name": "想法孵化器", "confidence": 50}]

        # 按置信度降序排序
        sorted_roles = sorted(valid_scores, key=lambda x: x[1], reverse=True)

        # 选择前top_k个角色
        top_roles = []
        for i, (role_name, confidence) in enumerate(sorted_roles[:top_k]):
            top_roles.append({"role_name": role_name, "confidence": confidence})

        return top_roles

    def role_router(self, user_input: str) -> List[Dict[str, Any]]:
        """思维模式路由器 - 识别并返回前2个最匹配的角色

        实现角色识别和选择的完整流程：
        1. 调用_identify_role_mode()进行第一阶段角色识别
        2. 调用_select_top_roles()选择前2个最匹配的角色

        Args:
            user_input: 用户输入的文本

        Returns:
            List[Dict[str, Any]]: 包含role_name和confidence字段的前2个角色列表
        """
        # 第一阶段：角色模式识别和评分
        role_scores = self._identify_role_mode(user_input)

        # 选择前2个最高分角色
        top_roles = self._select_top_roles(role_scores, top_k=2)

        return top_roles

    # endregion

    # region 辅助功能

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

    # endregion
