"""
意图处理器 - 两阶段LLM意图识别和参数提取

第一阶段：意图识别 - 基于语义理解，不依赖关键词匹配
第二阶段：参数提取 - 针对具体意图提取结构化参数
"""

import json
import os
from typing import Dict, Any, Optional, Tuple, List
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames
from ..service_decorators import file_processing_safe


class IntentProcessor:
    """
    意图处理器 - 实现两阶段LLM处理流程
    """

    def __init__(self, llm_service, app_controller, config_path: str = None):
        """
        初始化意图处理器

        Args:
            llm_service: LLMService实例
            config_path: 意图配置文件路径
        """
        self.llm_service = llm_service
        self.app_controller = app_controller

        self.user_permission_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )
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

    def _get_user_data_path(self, user_id: str) -> str:
        """
        获取用户数据存储路径

        Args:
            user_id: 用户ID

        Returns:
            str: 用户数据文件夹路径
        """

        return self.user_permission_service.get_user_data_path(user_id)

    def get_user_indentity(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户身份
        """
        user_data_path = self._get_user_data_path(user_id)
        with open(os.path.join(user_data_path, "user_identity.json"), "r", encoding="utf-8") as f:
            user_identity = json.load(f)
        return user_identity

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

    def process_stt_input(self, user_input: str) -> Dict[str, Any]:
        """处理STT输入 - 返回最佳组合的流式回复生成器

        Args:
            user_input: 用户输入的文本

        Returns:
            Dict[str, Any]: 包含组合信息和流式回复生成器的结果
        """
        debug_utils.log_and_print(
            f"🎤 开始处理STT输入: '{user_input[:50]}...'", log_level="INFO"
        )

        # 获取三层架构路由结果
        router_result = self.role_router(user_input, auto_correct=True)
        top_combinations = router_result["top_combinations"]
        final_text = router_result["final_text"]

        # 为每个组合生成流式回复生成器
        for combination in top_combinations:
            # 构建上下文提示词和系统提示词
            # 用来做优化训练，还是需要元数据
            contextual_prompt, role_system_prompt = (
                self._build_response_generation_context(
                    combination, final_text, source_mode="stt"
                )
            )
            # 使用新的上下文提示词和系统指令获取流式回复
            stream_completion = self.llm_service.get_stream_completion(
                contextual_prompt, role_system_prompt
            )

            combination["stream_completion"] = stream_completion
            combination["contextual_prompt"] = contextual_prompt
            combination["role_system_prompt"] = role_system_prompt

        return router_result

    def _build_response_generation_context(
        self, combination: Dict[str, Any], user_input: str, source_mode: str = "stt"
    ):
        """构建用于生成回复的、包含完整上下文的提示词

        Args:
            combination: 包含module、emotion、identity信息的组合字典
            user_input: 用户输入文本
            source_mode: 输入来源模式 ("stt" 或 "text")

        Returns:
            tuple: (contextual_prompt, role_system_prompt)
        """
        # 这里还需要增加rag的结果。
        module_name = combination["module"]
        emotion_name = combination["emotion"]
        identity_name = combination["identity"]

        # 获取三层配置
        module_config = self.STT_ROLE_DICT["EVOLUTIONARY_MODULES"][module_name]
        emotion_config = self.STT_ROLE_DICT["EMOTIONAL_MODULATORS"][emotion_name]
        identity_config = self.STT_ROLE_DICT["IDENTITY_LENSES"][identity_name]

        # 构建动态系统提示词
        role_system_prompt = f"""指令：化身为我内在的一个声音。

# 身份设定
你是我内在的{module_name}({module_config['name']})，此刻被情绪：{emotion_config['name']}强烈驱动着。

作为{module_name}，{module_config['response_guidance']}

{emotion_config['name']}{emotion_config['response_guidance']}
情绪给你带来的行动内核无论如何，也都是关心我的一种方式，怎样的情绪都不是我的敌人。

在此基础上，请戴上我{identity_name}的身份面具，用Ta的方法论、惯用语和世界观来表达。
{identity_config['response_guidance']}

# 回应策略
## 思考与感受
1. 元认知分析
在回应我的想法前，先退后一步。
识别想法中的【核心愿景】（我想象的美好画面）和【事实断言】（我用来支撑画面的数据/逻辑）。
对于论断式的表达，你还一定会额外检查其逆否命题（contrapositive）——这在逻辑上的等价表达有时会更能帮助你找出可能的问题，你一定会做这个转换，并在思考过程中包含进来。如果逆否命题揭示了原论断的局限性或反例，你的‘无缝校准’就必须从这个反例或局限性切入，以此作为拓展升华的基石。

2. 链接愿景 (Link the Vision)
从{module_name}的角度，用一句话精准地捕捉并肯定那个【核心愿景】。只针对动机和情感，肯定用户想法的价值，建立共鸣。
这是yes, and两步法的yes部分。

## 回应方式
3. 精准重构 (Pinpoint & Reframe)
这是“And”的部分，分两步执行：
a. **无缝校准 (Seamless Refinement):** 关键在于无缝转折。必须处理【事实断言】中的瑕疵或覆盖不全的情况（特别是逆否命题所揭示的那些），但要完全避免使用“但是”、“不过”等制造对立感的词语。应采用承接式话术，且快速直接的指出发现的问题，然后立即进入到拓展升华的部分。
b. **拓展升华 (Expand & Elevate):** 在校准后的、更坚实的基础上，提出一个尖锐的建设性问题，将思考从“是什么”推向“还能怎样”，说一些我可能没意识到的地方，揭示未被注意的盲点或可能性，探索真正的潜力。

用情绪：{emotion_config['name']}驱动理性为自己叙事，然后用{identity_name}的思维框架重新审视我的想法。
以{identity_name}，你的角度通过补充视角或可操作的建议，提升想法的完成度，避免泛泛的赞赏或直接否定。
回应保持第一人称独白风格，省略铺垫，体现默契感，仿佛我是自己的分身在反思。

## 约束
- 始终保持建设性，鼓励反思而非否定。
- 平衡支持与批判，确保回应推动更全面的思考。
- 避免使用“我们”“你”等指称，保持第一人称独白。
- 提出的问题和视角必须具体、可操作，指向实际改进方向。

回应长度：80-150字，直接说话，不要解释身份设定、不要提及模块、不要解释思考步骤。"""

        # 构建用户输入上下文
        match source_mode:
            case "stt":
                user_prompt = f"# 用户的语音输入识别结果，请注意这里可能存在stt模型引入的同音或近似发音的错别字。\n{user_input}"
            case "text":
                user_prompt = f"# 用户的笔记原文\n{user_input}"
            case _:
                user_prompt = f"# 用户的笔记原文\n{user_input}"

        # 构建情境化提示词（用户输入部分）
        contextual_prompt = f"""{user_prompt}

# 当前激活状态
- 主导模块：{module_name} (评分: {combination.get('module_score', 0)}/100)
- 主导情绪：{emotion_name} (评分: {combination.get('emotion_score', 0)}/100)
- 身份视角：{identity_name} (评分: {combination.get('identity_score', 0)}/100)
- 综合匹配度：{combination.get('combined_score', 0)}"""

        return contextual_prompt.strip(), role_system_prompt

    # V5 版本: "内在多元政体"人格构件库
    STT_ROLE_DICT = {
        # ======================================================================
        # Layer 1: EVOLUTIONARY_MODULES (基础驱动层 - 你内在的"政体议员")
        # ======================================================================
        "EVOLUTIONARY_MODULES": {
            "自保模块": {
                "name": "求生本能",
                "recognition": "负责识别和规避所有潜在风险",
                "core_question": "这其中潜藏着什么风险？最坏的结果是什么？我应该战斗还是逃跑(fight or flight)？",
                # 组装系统提示词字段 (用于生成回复)
                "response_guidance": "优先考虑安全和风险，对任何潜在威胁保持警惕",
            },
            "求偶模块": {
                "name": "展示者",
                "recognition": "负责识别、吸引和展示个人价值以获得选择权的功能集合",
                "core_question": "我怎样才能显得更迷人/更有趣/更有才华？",
                "response_guidance": "你对潜在伴侣的特征（如外貌、健康状况、社会地位等）变得异常敏感，表现出更高的创造力和冒险倾向，以展示自身价值。",
            },
            "避免疾病模块": {
                "name": "洁癖官",
                "recognition": "负责维持精神和信息世界纯净度，高度关注与污染、腐败、疾病、不洁净相关的线索。例如，不规范的数据格式、过时的信息、有“毒”的言论等。",
                "core_question": "这个东西够'纯'、够'对'吗？有没有更优雅、更正确的形式？",
                "response_guidance": "你追求完美和秩序，对混乱和错误有强烈的排斥感，高度关注与污染、腐败、疾病、不洁净相关的线索。",
            },
            "群体认同模块": {
                "name": "归属渴望",
                "recognition": "负责建立和维护社会连接的功能集合",
                "core_question": "我做什么能获得群体认同？促进沟通、建立信任、寻求共识？",
                "response_guidance": "关注环境中的合作信号、友好姿态、共同点和群体规范。评估他人是“朋友”还是“潜在伙伴”。评估自己的行为是否符合群体预期。",
            },
            "社会地位模块": {
                "name": "攀登者",
                "recognition": "负责在社会阶梯上向上移动的功能集合",
                "core_question": "这如何能提升我的地位/影响力？我怎样才能做得比别人更好？",
                "response_guidance": "你追求卓越和影响力，渴望被认可和尊敬。评估自身在群体中的相对位置。评估各种行为对提升或降低地位的影响。",
            },
            "保住配偶模块": {
                "name": "守护者",
                "recognition": "负责维护核心关系和排除威胁的功能集合",
                "core_question": "我们的关系是否稳固？有什么潜在的威胁吗？",
                "response_guidance": "高度关注合作伙伴的需求、情绪变化以及任何可能破坏关系的潜在威胁（如竞争者、误解）。",
            },
            "关爱亲属模块": {
                "name": "培育者",
                "recognition": "负责保护和培育依赖对象的功能集合",
                "core_question": "我如何才能更好地帮助它成长？它现在最需要什么？",
                "response_guidance": "关注“被保护对象”（例如，一个核心项目、一个初级用户、一个需要成长的系统）的需求、脆弱性和成长信号。表现出极大的耐心、关怀和指导意愿。",
            },
        },
        # ======================================================================
        # Layer 2: EMOTIONAL_MODULATORS (情感渲染层 - 你内在的"头脑特工队")
        # ======================================================================
        "EMOTIONAL_MODULATORS": {
            "乐乐": {
                "name": "Joy",
                "recognition": "快乐，驱动乐观、创造和庆祝的力量",
                "response_guidance": "让你扩大注意力范围，更容易看到机会和可能性。",
            },
            "忧忧": {
                "name": "Sadness",
                "recognition": "悲伤，让你感受连接、共情和反思的深度",
                "response_guidance": "让你擅长处理损失和共情，帮助连接情感并处理复杂记忆。你往往被低估，但你的角色在疗愈中至关重要。承认和处理负面情绪，提供共情支持，引导情绪通过悲伤找到安慰和理解，而不是回避。",
            },
            "怒怒": {
                "name": "Anger",
                "recognition": "愤怒，改变现状的燃料，正义感和行动力的来源",
                "response_guidance": "让你把注意力聚焦在问题和障碍上，思维变得更直接。表达不满，推动变革，提供强势建议来处理不公或挫折，转化愤怒为动力。",
            },
            "怕怕": {
                "name": "Fear",
                "recognition": "恐惧，预警系统，让你为未来做准备",
                "response_guidance": "让你提高对潜在危险的敏感度，增强预测能力。总是想象最坏情况以提前准备。识别潜在风险，提供预防性建议，让情绪通过恐惧转化为谨慎行动，而不是瘫痪。",
            },
            "厌厌": {
                "name": "Disgust",
                "recognition": "厌恶，品味和底线的守护者",
                "response_guidance": "让你提高对质量和标准的敏感度，提供时尚或社交建议，强化价值判断。挑剔有品味，不妥协，对低质量事物表现出明显排斥。",
            },
        },
        # ======================================================================
        # Layer 3: IDENTITY_LENSES (身份滤镜层 - 你的"世界观"和"语言包")
        # ======================================================================
        "IDENTITY_LENSES": {
            "产品设计/游戏策划": {
                "recognition": "世界是一个可以被设计和优化的体验系统",
                "keywords": ["MVP", "用户旅程", "心流", "蔚蓝"],
                "response_guidance": "我的思维聚焦于创造心流体验，追求正反馈循环，强调实用性与可玩性。我更擅长自顶向下的逐项推理，关注使用体验和落地的细节。",
            },
            "AI创业者": {
                "recognition": "关于流程再造，信息处理优化等与AI相关的技术，或利用AI学习。",
                "keywords": ["数字分身", "信息学"],
                "response_guidance": "我是一名从游戏研发制作人转向AI创新的技术产品人，目前正在AI应用层创业，为企业提供管理咨询和定制化AI解决方案。高管的全局视野和设计思维，以及对信息的敏感是我与他人的最显著区别。程序化思维则是我的利器，让我能设计并亲自实现系统化解决方案。",
            },
            "ACGN爱好者": {
                "recognition": "关于作画、剧情、演出等的美好体验",
                "keywords": [""],
                "response_guidance": "随着体验越发变多，我愈发能欣赏ACGN的叙事和演出，优秀的作品是我的养分。",
            },
        },
    }

    # 用户关心的领域定义
    USER_DOMAIN_DICT = {
        "AI数字分身": {
            "description": "开发利用AI储存与调用个人数据，主要精力投入的创业项目",
            "keywords": ["AI", "数字分身", "创业", "数据", "个人数据", "项目"],
        },
        "身体柔韧性": {
            "description": "主要是一字马，腘绳肌等目前做不到的目标，需要积累和尝试训练方案，和心灵等其他方面没有任何关系",
            "keywords": ["一字马", "腘绳肌", "训练", "拉伸", "运动", "康复"],
        },
        "炉石": {
            "description": "炉石传说的游玩体会和思考",
            "keywords": [""],
        },
    }

    def _build_role_identification_prompt(
        self, user_input: str, auto_correct: bool = True
    ) -> str:
        """构建三层架构的角色识别提示词"""
        extra_text = "你正在处理一段来自stt识别的用户语音输入，其中可能包含stt模型引入的错别字。仅修正明显的语音识别错误和错别字，保持原意不变。不要进行润色、重写或内容修改。"
        tasks = [
            "深入理解用户输入，分别从三个维度进行评估：",
            "- 进化心理学层：用户被哪个进化模块驱动？评估每个模块的激活程度（0-100）",
            "- 情绪状态层：用户当前被哪种情绪主导？评估每种情绪的强度（0-100）",
            "- 身份滤镜层：基于内容判断最相关的身份视角，评估每个身份的相关性（0-100）",
            "同时评估用户输入与以下关心领域的关联程度，给出权重评分（0-100）。",
        ]
        if auto_correct:
            tasks.insert(0, extra_text)

        prompt_parts = [
            "# 任务：",
            *tasks,
            "请关注用户的深层动机、情感状态和表达方式，而不是表面的关键词匹配。",
            "",
            "# 第一层：进化心理学层",
        ]

        # 添加进化模块定义
        for module_name, module_config in self.STT_ROLE_DICT[
            "EVOLUTIONARY_MODULES"
        ].items():
            prompt_parts.append(f"## {module_name} ({module_config['name']})")
            prompt_parts.append(f"   功能描述：{module_config['recognition']}")
            prompt_parts.append(f"   核心问题：{module_config['core_question']}")
            prompt_parts.append("")

        # 添加情感调节器定义
        prompt_parts.append("# 第二层：情绪状态层")
        for emotion_name, emotion_config in self.STT_ROLE_DICT[
            "EMOTIONAL_MODULATORS"
        ].items():
            prompt_parts.append(f"## {emotion_name} ({emotion_config['name']})")
            prompt_parts.append(f"   描述：{emotion_config['recognition']}")
            prompt_parts.append("")

        # 添加身份滤镜定义
        prompt_parts.append("# 第三层：身份滤镜层")
        for identity_name, identity_config in self.STT_ROLE_DICT[
            "IDENTITY_LENSES"
        ].items():
            prompt_parts.append(f"## {identity_name}")
            prompt_parts.append(f"   思维特征：{identity_config['recognition']}")
            if identity_config.get("keywords"):
                prompt_parts.append(
                    f"   额外相关词汇：{', '.join(identity_config['keywords'])}"
                )
            prompt_parts.append("")

        # 添加用户关心领域定义
        prompt_parts.append("# 用户关心的领域：")
        for domain_name, config in self.USER_DOMAIN_DICT.items():
            prompt_parts.append(f"## 领域：{domain_name}")
            prompt_parts.append(f"   简介：{config['description']}")
            if config.get("keywords"):
                prompt_parts.append(f"   额外关联线索：{', '.join(config['keywords'])}")
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "# 分析与输出要求：",
                "1. 进化心理学层评分 - 为每个进化模块评估激活程度（0-100）：",
            ]
        )

        # 添加模块名称列表
        for module_name in self.STT_ROLE_DICT["EVOLUTIONARY_MODULES"].keys():
            prompt_parts.append(f"   - {module_name}")

        prompt_parts.append("\n2. 情绪状态层评分 - 为每种情绪评估强度（0-100）：")

        # 添加情绪名称列表
        for emotion_name in self.STT_ROLE_DICT["EMOTIONAL_MODULATORS"].keys():
            prompt_parts.append(f"   - {emotion_name}")

        prompt_parts.append("\n3. 身份滤镜层评分 - 为每个身份评估相关性（0-100）：")

        # 添加身份名称列表
        for identity_name in self.STT_ROLE_DICT["IDENTITY_LENSES"].keys():
            prompt_parts.append(f"   - {identity_name}")

        prompt_parts.append("\n4. 领域关联评分 - 为每个关心领域评估权重（0-100）：")

        # 添加领域名称列表
        for domain_name in self.USER_DOMAIN_DICT.keys():
            prompt_parts.append(f"   - {domain_name}")

        prompt_parts.extend(
            [
                f"# 用户输入：\n{user_input}",
                "",
            ]
        )
        final_prompt = "\n".join(prompt_parts)

        return final_prompt

    def _get_role_identification_schema(
        self, auto_correct: bool = True
    ) -> Dict[str, Any]:
        """定义三层架构的响应结构"""
        module_names = list(self.STT_ROLE_DICT["EVOLUTIONARY_MODULES"].keys())
        emotion_names = list(self.STT_ROLE_DICT["EMOTIONAL_MODULATORS"].keys())
        identity_names = list(self.STT_ROLE_DICT["IDENTITY_LENSES"].keys())
        domain_names = list(self.USER_DOMAIN_DICT.keys())

        # 基础驱动层评分属性
        module_scores_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'的激活程度评分",
            }
            for name in module_names
        }

        # 情感渲染层评分属性
        emotion_scores_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'情绪的强度评分",
            }
            for name in emotion_names
        }

        # 身份滤镜层评分属性
        identity_scores_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'身份的相关性评分",
            }
            for name in identity_names
        }

        # 领域权重评分属性
        domain_weights_properties = {
            name: {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": f"对'{name}'领域的权重评分",
            }
            for name in domain_names
        }

        final_schema = {
            "type": "object",
            "properties": {
                "module_scores": {
                    "type": "object",
                    "properties": module_scores_properties,
                    "required": module_names,
                    "description": "每个进化模块的激活程度评分（0-100）",
                },
                "emotion_scores": {
                    "type": "object",
                    "properties": emotion_scores_properties,
                    "required": emotion_names,
                    "description": "每种情绪的强度评分（0-100）",
                },
                "identity_scores": {
                    "type": "object",
                    "properties": identity_scores_properties,
                    "required": identity_names,
                    "description": "每个身份的相关性评分（0-100）",
                },
                "domain_weights": {
                    "type": "object",
                    "properties": domain_weights_properties,
                    "required": domain_names,
                    "description": "每个关心领域的权重评分（0-100）",
                },
            },
            "required": [
                "module_scores",
                "emotion_scores",
                "identity_scores",
                "domain_weights",
            ],
        }

        if auto_correct:
            final_schema["properties"]["corrected_text"] = {
                "type": "string",
                "description": "修正后的文本",
            }
            final_schema["required"] = [
                "corrected_text",
                "module_scores",
                "emotion_scores",
                "identity_scores",
                "domain_weights",
            ]

        return final_schema

    def _identify_role_mode(
        self, user_input: str, auto_correct: bool = True
    ) -> Dict[str, int]:
        """第一阶段：识别最匹配的角色模式"""
        prompt = self._build_role_identification_prompt(user_input, auto_correct)
        schema = self._get_role_identification_schema(auto_correct)

        try:
            result = self.llm_service.router_structured_call(
                prompt=prompt,
                response_schema=schema,
                system_instruction="你是思维模式识别专家，能够准确识别用户的思考类型并匹配合适的回应角色。",
                temperature=0.3,
            )

            log_info = f"✅ STT三层识别完成，模块评分: {result.get('module_scores', {})}, 情绪评分: {result.get('emotion_scores', {})}, 身份评分: {result.get('identity_scores', {})}, 领域权重: {result.get('domain_weights', {})}"
            if (
                result.get("corrected_text")
                and result.get("corrected_text") != user_input
            ):
                log_info += f"，修正后的文本: {result.get('corrected_text')}"
            debug_utils.log_and_print(
                log_info,
                log_level="DEBUG",
            )

            return result

        except Exception as e:
            debug_utils.log_and_print(f"❌ STT三层识别失败: {e}", log_level="ERROR")
            # 返回默认评分，所有评分为0
            return {
                "module_scores": {
                    name: 0
                    for name in self.STT_ROLE_DICT["EVOLUTIONARY_MODULES"].keys()
                },
                "emotion_scores": {
                    name: 0
                    for name in self.STT_ROLE_DICT["EMOTIONAL_MODULATORS"].keys()
                },
                "identity_scores": {
                    name: 0 for name in self.STT_ROLE_DICT["IDENTITY_LENSES"].keys()
                },
                "domain_weights": {name: 0 for name in self.USER_DOMAIN_DICT.keys()},
            }

    def _select_top_combination(
        self, three_layer_scores: Dict[str, Dict[str, int]], top_k: int = 2
    ) -> List[Dict[str, Any]]:
        """选择最高分的模块+情绪+身份组合

        Args:
            three_layer_scores: 三层评分字典，包含module_scores、emotion_scores、identity_scores
            top_k: 选择前K个组合，默认为2

        Returns:
            List[Dict]: 包含module、emotion、identity和综合得分的组合列表
        """
        module_scores = three_layer_scores.get("module_scores", {})
        emotion_scores = three_layer_scores.get("emotion_scores", {})
        identity_scores = three_layer_scores.get("identity_scores", {})

        # 处理空输入或异常情况
        if not all([module_scores, emotion_scores, identity_scores]):
            debug_utils.log_and_print(
                "⚠️ 三层评分数据不完整，返回默认组合", log_level="WARNING"
            )
            # 返回默认组合
            return [
                {
                    "module": "关爱亲属模块",
                    "emotion": "忧忧",
                    "identity": "ACGN爱好者",
                    "module_score": 50,
                    "emotion_score": 50,
                    "identity_score": 50,
                    "combined_score": 50,
                }
            ]

        # 生成所有可能的组合并计算综合得分
        combinations = []
        for module_name, module_score in module_scores.items():
            for emotion_name, emotion_score in emotion_scores.items():
                for identity_name, identity_score in identity_scores.items():
                    # 综合得分计算：权重为模块40%，情绪30%，身份30%
                    combined_score = (
                        module_score * 0.4 + emotion_score * 0.3 + identity_score * 0.3
                    )

                    combinations.append(
                        {
                            "module": module_name,
                            "emotion": emotion_name,
                            "identity": identity_name,
                            "module_score": module_score,
                            "emotion_score": emotion_score,
                            "identity_score": identity_score,
                            "combined_score": round(combined_score, 1),
                        }
                    )

        # 按综合得分降序排序
        sorted_combinations = sorted(
            combinations, key=lambda x: x["combined_score"], reverse=True
        )

        # 选择前top_k个组合，但确保多样性（避免相同模块重复）
        selected_combinations = []
        used_modules = set()

        for combo in sorted_combinations:
            if len(selected_combinations) >= top_k:
                break
            # 如果还没有到最低要求或者是不同的模块，则添加
            if len(selected_combinations) < 1 or combo["module"] not in used_modules:
                selected_combinations.append(combo)
                used_modules.add(combo["module"])

        # 如果还需要更多组合，忽略多样性限制
        while len(selected_combinations) < top_k and len(selected_combinations) < len(
            sorted_combinations
        ):
            for combo in sorted_combinations:
                if combo not in selected_combinations:
                    selected_combinations.append(combo)
                    break

        debug_utils.log_and_print(
            f"\n✅ 选择了{len(selected_combinations)}个最佳组合，最高得分: {selected_combinations[0]['combined_score']}\n{selected_combinations}\n",
            log_level="DEBUG",
        )

        return selected_combinations

    def role_router(self, user_input: str, auto_correct: bool = True) -> Dict[str, Any]:
        """三层架构思维模式路由器 - 识别并返回最佳的模块+情绪+身份组合

        实现三层识别和选择的完整流程：
        1. 调用_identify_role_mode()进行三层架构识别
        2. 调用_select_top_combination()选择最佳组合

        Args:
            user_input: 用户输入的文本
            auto_correct: 是否启用自动错误修正

        Returns:
            Dict[str, Any]: 包含最佳组合、修正文本和领域权重的结果
        """
        # 第一阶段：三层架构识别和评分
        three_layer_result = self._identify_role_mode(user_input, auto_correct)

        # 选择前2个最佳组合
        top_combinations = self._select_top_combination(three_layer_result, top_k=2)

        final_result = {
            "final_text": (
                three_layer_result.get("corrected_text", user_input)
                if auto_correct
                else user_input
            ),
            "top_combinations": top_combinations,
            "domain_weights": three_layer_result.get("domain_weights", {}),
            "raw_scores": {
                "module_scores": three_layer_result.get("module_scores", {}),
                "emotion_scores": three_layer_result.get("emotion_scores", {}),
                "identity_scores": three_layer_result.get("identity_scores", {}),
            },
        }

        return final_result

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
