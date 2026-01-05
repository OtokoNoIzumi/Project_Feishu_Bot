"""
飞书消息处理器 (Feishu Message Handler)

负责处理飞书消息事件，包括：
- 消息接收和转换
- 异步操作处理
- 特殊响应类型处理
"""

import json
import threading
from typing import Optional, Any, Dict
import time
import base64
import os
import urllib.request
import urllib.error

from google.genai.types import FinishReason

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import (
    MessageContext,
    ProcessResult,
    MessageContext_Refactor,
    TextContent,
    FileContent,
    PostContent,
    RouteResult,
)
from ..decorators import (
    feishu_event_handler_safe,
    message_conversion_safe,
    async_operation_safe,
)
from ..utils import extract_timestamp, noop_debug, ROUTE_KNOWLEDGE_MAPPING
from Module.Adapters.feishu.cards.json_builder import JsonBuilder
from Module.Services.constants import (
    ServiceNames,
    UITypes,
    ResponseTypes,
    Messages,
    CardOperationTypes,
    ProcessResultConstKeys,
    ProcessResultNextAction,
    AdapterNames,
    CardConfigKeys,
)


class MessageHandler:
    """飞书消息处理器"""

    THOUGHT_ANIMATION = ["正在思考", "正在思考.", "正在思考..", "正在思考..."]

    # region 初始化
    def __init__(self, app_controller, message_router, sender, debug_functions=None):
        """
        初始化消息处理器

        Args:
            app_controller: 应用控制器实例
            message_router: 业务消息路由器
            sender: 消息发送器实例
            debug_functions: 调试函数字典，包含debug_p2im_object等
        """
        self.message_router = message_router
        self.sender = sender

        # 获取应用控制器以访问服务
        self.app_controller = app_controller
        self.debug_p2im_object = debug_functions.get("debug_p2im_object", noop_debug)
        self.debug_parent_id_analysis = debug_functions.get(
            "debug_parent_id_analysis", noop_debug
        )
        self.card_handler = None  # 将由adapter注入
        self.cache_service = self.app_controller.get_service(ServiceNames.CACHE)
        self.user_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )

    def set_card_handler(self, card_handler):
        """注入CardHandler实例"""
        self.card_handler = card_handler

    def _execute_async(self, func):
        """执行异步操作的通用方法"""
        thread = threading.Thread(target=func)
        thread.daemon = True
        thread.start()

    # endregion

    # region 消息处理入口

    @feishu_event_handler_safe("处理飞书消息失败")
    def handle_feishu_message(self, data) -> None:
        """
        处理飞书消息事件

        将飞书消息转换为标准消息上下文，调用业务处理器处理，
        并根据处理结果决定回复方式（普通回复、异步处理、特殊类型）
        目前的标准步骤有3个
        1 转换为标准消息上下文
        2 调用业务处理器-得到ProcessResult
          2.1 识别ProcessResult中的异步操作，那么这个结果本身不包含更多业务数据，前置发送一个确认信息，然后做异步处理，得到最终的ProcessResult
        3 根据ProcessResult中的response_type，决定回复方式/调用卡片
        """
        # 转换为标准消息上下文
        conversion_result = self._convert_message_to_context(data)

        context, context_refactor = conversion_result

        if self.sender.filter_duplicate_message(context_refactor):
            return

        # 分离一些和业务无关的逻辑出来，比如消息去重。
        # 调用业务消息路由器
        result = self.message_router.process_message(context)

        if isinstance(result, RouteResult):
            # 向后兼容在这里处理新的业务。
            # 参考handle_feishu_card的配置驱动模式，避免硬编码
            self.handle_route_result_dynamic(result, context_refactor)
            return

        # 检查是否需要异步处理
        if self._handle_async_actions(data, result, context_refactor):
            return

        # 检查特殊响应类型
        if self._handle_special_response_types(data, result, context, context_refactor):
            return
        # 普通回复
        if result.should_reply:
            self.sender.send_feishu_reply(data, result)

    # endregion

    # region 结果处理-路由

    def handle_route_result_dynamic(
        self, route_result: RouteResult, context_refactor: MessageContext_Refactor
    ):
        """
        动态处理RouteResult - 基于路由知识映射进行分发
        实现业务层与适配器层的分离：业务层只提供标识，适配器层管理前端知识

        Args:
            route_result: 路由结果，包含业务标识和业务参数
            context_refactor: 重构后的消息上下文
        """
        try:
            # 先发送前置消息（如果有）
            if route_result.message_before_async:
                self.sender.send_feishu_message_reply(
                    context_refactor, route_result.message_before_async
                )

            # 从路由知识映射获取前端处理方式
            route_knowledge = ROUTE_KNOWLEDGE_MAPPING.get(route_result.route_type)

            if not route_knowledge:
                debug_utils.log_and_print(
                    f"未知的路由类型: {route_result.route_type}", log_level="ERROR"
                )
                error_result = ProcessResult.error_result(
                    f"未知的路由类型: {route_result.route_type}"
                )
                self.sender.send_feishu_reply_with_context(
                    context_refactor, error_result
                )
                return

            # 获取处理器对象 - 支持三个handler的配置
            handler_name = route_knowledge["handler"]
            handler_mapping = {
                "message_handler": self,
                "card_handler": self.card_handler,
                # "menu_handler": getattr(self, 'menu_handler', None)
            }
            handler = handler_mapping.get(handler_name)
            if not handler:
                debug_utils.log_and_print(
                    f"未找到处理器: {handler_name}", log_level="ERROR"
                )
                error_result = ProcessResult.error_result(
                    f"未找到处理器: {handler_name}"
                )
                self.sender.send_feishu_reply_with_context(
                    context_refactor, error_result
                )
                return

            # 获取处理方法
            method_name = route_knowledge["method"]
            method = getattr(handler, method_name, None)
            if not method:
                debug_utils.log_and_print(
                    f"未找到方法: {handler_name}.{method_name}", log_level="ERROR"
                )
                error_result = ProcessResult.error_result(
                    f"未找到方法: {handler_name}.{method_name}"
                )
                self.sender.send_feishu_reply_with_context(
                    context_refactor, error_result
                )
                return

            # 结构化参数解析：分离不同来源的参数
            call_params = route_knowledge.get("call_params", {})  # 前端知识参数
            system_params = {  # 系统必须参数
                "result": route_result,
                "context_refactor": context_refactor,
            }
            business_params = route_result.route_params  # 业务参数

            # 构造最终调用参数：优先级 系统 > 前端知识 > 业务
            kwargs = {
                **call_params,  # 前端知识参数（低优先级）
                **business_params,  # 业务参数（中优先级）
                **system_params,  # 系统参数（高优先级）
            }
            # Notion解析失败的时候这里也会报错 【待增加兼容
            # 执行调用
            if route_knowledge.get("is_async", False):
                # 异步执行
                def process_in_background():
                    method(**kwargs)

                self._execute_async(process_in_background)
            else:
                # 同步执行
                method(**kwargs)
            return

        except Exception as e:
            debug_utils.log_and_print(f"路由分发处理异常: {str(e)}", log_level="ERROR")
            error_result = ProcessResult.error_result(f"路由分发处理异常: {str(e)}")
            self.sender.send_feishu_reply_with_context(context_refactor, error_result)

    # endregion

    # region 结果处理-异步

    def _handle_async_actions(
        self, data, result: ProcessResult, context_refactor: MessageContext_Refactor
    ) -> bool:
        """处理异步操作，返回True表示已处理"""

        # 异步操作映射表，直接映射到处理逻辑——后续要换成配置
        action_handlers = {
            ProcessResultNextAction.PROCESS_TTS: lambda: self._handle_tts_async(
                data, result.response_content.get("tts_text", "")
            ),
            ProcessResultNextAction.PROCESS_IMAGE_GENERATION: lambda: self._handle_image_generation_async(
                data, result.response_content.get("generation_prompt", "")
            ),
            ProcessResultNextAction.PROCESS_IMAGE_CONVERSION: lambda: self._handle_image_conversion_async(
                data
            ),
            ProcessResultNextAction.PROCESS_AUDIO_STT: lambda: self._handle_audio_stt_async(
                context_refactor
            ),
            ProcessResultNextAction.PROCESS_DIET_ANALYZE: lambda: self._handle_diet_analyze_async(
                data, context_refactor, result.response_content
            ),
        }

        if result.response_type == ResponseTypes.ASYNC_ACTION:
            # 根据reply_message_type决定发送方式，为后续卡片切换预留
            reply_type = getattr(result, "reply_message_type", None)
            match reply_type:
                case "text":
                    self.sender.send_feishu_reply_with_context(context_refactor, result)
                case "card":
                    # 在这里先跑通再找地方
                    card_header = JsonBuilder.build_card_header(
                        title="智能语音识别",
                    )
                    card_body_elements = [
                        JsonBuilder.build_markdown_element(
                            content=result.message_before_async,
                            text_size="normal",
                            element_id="audio_stt_result",
                        )
                    ]
                    business_data = {
                        "markdown_element_id": "audio_stt_result",
                    }
                    card_data = JsonBuilder.build_stream_card_structure(
                        card_body_elements, card_header
                    )

                    card_content = {"type": "card_json", "data": card_data}
                    card_id = self.sender.create_card_entity(card_content)
                    if card_id:
                        card_content = {
                            "type": "card",
                            "data": {"card_id": card_id},
                        }
                        result.response_type = ResponseTypes.INTERACTIVE

                        self.user_service.save_new_card_business_data(
                            context_refactor.user_id, card_id, business_data
                        )

                    send_params = {
                        "card_content": card_content,
                        "reply_mode": "reply",
                        "user_id": context_refactor.user_id,
                        "message_id": context_refactor.message_id,
                    }
                    success, message_id = self.sender.send_interactive_card(
                        **send_params
                    )

                    context_refactor.metadata["message_id"] = message_id
                    # 这样在后续的_handle_audio_stt_async中就能正确获取到卡片信息
                    self.cache_service.update_message_id_card_id_mapping(
                        message_id, card_id, "audio_stt_result"
                    )
                    self.cache_service.save_message_id_card_id_mapping()

                case _:
                    self.sender.send_feishu_reply_with_context(context_refactor, result)

            async_action = action_handlers.get(result.async_action)
            if async_action:
                async_action()
                return True

        if not (result.success and result.response_content):
            return False

        next_action = result.response_content.get(ProcessResultConstKeys.NEXT_ACTION)
        if not next_action:
            return False

        handler = action_handlers.get(next_action)
        if handler:
            handler()
            return True

        return False

    # endregion

    # region 具体业务

    @async_operation_safe("TTS异步处理失败")
    def _handle_tts_async(self, original_data, tts_text: str):
        """异步处理TTS任务"""

        def process_in_background():
            # 调用业务处理器的异步TTS方法
            result = self.message_router.media.process_tts_async(tts_text)

            if result.success and result.response_type == ResponseTypes.AUDIO:
                # 上传并发送音频
                audio_data = result.response_content.get("audio_data")
                if audio_data:
                    self.sender.upload_and_send_audio(original_data, audio_data)
                else:
                    # 音频数据为空，发送错误提示
                    error_result = ProcessResult.error_result("音频生成失败，数据为空")
                    self.sender.send_feishu_reply(original_data, error_result)
            else:
                # TTS处理失败，发送错误信息
                self.sender.send_feishu_reply(original_data, result)

        self._execute_async(process_in_background)

    @async_operation_safe("图像生成异步处理失败")
    def _handle_image_generation_async(self, original_data, prompt: str):
        """异步处理图像生成任务"""

        def process_in_background():
            # 先发送处理中提示
            processing_result = ProcessResult.success_result(
                ResponseTypes.TEXT, {"text": Messages.IMAGE_GENERATING}
            )
            self.sender.send_feishu_reply(original_data, processing_result)

            # 调用业务处理器的异步图像生成方法
            result = self.message_router.media.process_image_generation_async(prompt)

            if result.success and result.response_type == ResponseTypes.IMAGE_LIST:
                # 上传并发送图像
                image_paths = result.response_content.get("image_paths", [])
                error_msg = result.response_content.get("error_msg", "")
                if image_paths:
                    self.sender.upload_and_send_images(original_data, image_paths)
                if error_msg:
                    error_result = ProcessResult.error_result(error_msg)
                    self.sender.send_feishu_reply(original_data, error_result)
            else:
                # 图像生成失败，发送错误信息，业务优化应该已经不需要了
                self.sender.send_feishu_reply(original_data, result)

        self._execute_async(process_in_background)

    @async_operation_safe("图像转换异步处理失败")
    def _handle_image_conversion_async(self, original_data):
        """异步处理图像转换任务"""

        def process_in_background():
            # 先发送处理中提示
            processing_result = ProcessResult.success_result(
                "text", {"text": "正在转换图片风格，请稍候..."}
            )
            self.sender.send_feishu_reply(original_data, processing_result)

            # 获取图像资源
            image_resource = self.sender.get_image_resource(original_data)
            if not image_resource:
                error_result = ProcessResult.error_result("获取图片资源失败")
                self.sender.send_feishu_reply(original_data, error_result)
                return

            image_base64, mime_type, file_name, file_size = image_resource

            # 调用业务处理器的异步图像转换方法
            result = self.message_router.media.process_image_conversion_async(
                image_base64, mime_type, file_name, file_size
            )

            if result.success and result.response_type == "image_list":
                # 上传并发送图像
                image_paths = result.response_content.get("image_paths", [])
                if image_paths:
                    self.sender.upload_and_send_images(original_data, image_paths)
                else:
                    # 图像列表为空，发送错误提示
                    error_result = ProcessResult.error_result("图像转换失败，结果为空")
                    self.sender.send_feishu_reply(original_data, error_result)
            else:
                # 图像转换失败，发送错误信息
                self.sender.send_feishu_reply(original_data, result)

        self._execute_async(process_in_background)

    # endregion

    # region 饮食分析

    def _call_backend_diet_analyze(
        self, user_id: str, user_note: str, images_b64: list
    ) -> Dict[str, Any]:
        base_url = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
        token = os.getenv("BACKEND_INTERNAL_TOKEN", "").strip()

        payload = {
            "user_id": user_id,
            "user_note": user_note or "",
            "images_b64": images_b64 or [],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            url=f"{base_url}/api/diet/analyze",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if token:
            req.add_header("authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return (
                    json.loads(body)
                    if body
                    else {"success": False, "error": "Empty response"}
                )
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            return {
                "success": False,
                "error": f"HTTPError {e.code}: {body or e.reason}",
            }
        except Exception as e:
            return {"success": False, "error": f"Backend call failed: {e}"}

    @async_operation_safe("饮食分析异步处理失败")
    def _handle_diet_analyze_async(
        self, original_data, context: MessageContext_Refactor, payload: Dict[str, Any]
    ):
        def process_in_background():
            self.sender.send_feishu_reply(
                original_data,
                ProcessResult.success_result(
                    "text",
                    {"text": "正在分析饮食记录，请稍候..."},
                    parent_id=context.message_id,
                ),
            )

            user_note = (payload.get("diet_user_note") or "").strip()
            image_keys = payload.get("diet_image_keys") or []

            images_b64 = []
            for key in image_keys:
                img_bytes = self.sender.get_image_bytes(context.message_id, key)
                if not img_bytes:
                    continue
                images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))

            backend_resp = self._call_backend_diet_analyze(
                user_id=context.user_id, user_note=user_note, images_b64=images_b64
            )
            if not backend_resp.get("success"):
                err = backend_resp.get("error") or "饮食分析失败"
                self.sender.send_feishu_reply(
                    original_data, ProcessResult.error_result(str(err))
                )
                return

            result = backend_resp.get("result") or {}
            from Module.Adapters.feishu.cards.diet_cards import DietAnalysisCardBuilder

            card_data = DietAnalysisCardBuilder.build_card_dsl(result)

            card_content = {"type": "card_json", "data": card_data}
            card_id = self.sender.create_card_entity(card_content)
            if card_id:
                card_content = {"type": "card", "data": {"card_id": card_id}}

            self.sender.send_interactive_card(
                card_content=card_content,
                reply_mode="reply",
                user_id=context.user_id,
                message_id=context.message_id,
            )

        self._execute_async(process_in_background)

    # endregion

    # region 新业务-STT

    @async_operation_safe("音频STT异步处理失败")
    def _handle_audio_stt_async(self, context: MessageContext_Refactor):
        """异步处理音频STT任务"""

        def process_in_background():
            # 先发送处理中提示
            # 从response_content中获取音频相关信息
            # 语音的交互逻辑和点击毕竟有区别，可能要自动识别已经开启的任务并进入编辑模式？
            file_key = context.content.file_key
            message_id = context.message_id
            user_id = context.user_id
            timestamp = context.timestamp
            file_bytes = self.sender.get_file_resource(message_id, file_key)

            if not all([file_bytes, user_id, timestamp]):
                self.sender.send_feishu_message_reply(context, "音频处理参数不完整")
                return

            # 调用业务处理器的异步音频STT方法
            # 没必要用processresult这个结构？——主要是发送的部分，但外面应该还好。

            result = self.message_router.media.process_audio_stt_async(
                file_bytes, user_id, timestamp
            )

            card_message_id = context.metadata["message_id"]
            card_info = self.cache_service.get_card_info(card_message_id)

            card_id = card_info.get("card_id", "")
            sequence = card_info.get("sequence", "")
            # 音频的router在这里就直接开始处理识别好的参数构建在下面了。
            # 对于不是router的就沿用现在的打字机，但可以考虑做一个配音玩——这个应该是数字分身的环节。
            if isinstance(result, RouteResult):
                # 也不能直接用诶。。。这其实是发送新卡片，其实是我要把卡片元素编辑进去omg。
                # 如果我手动先省略掉跳转，直接编辑结果呢。
                # 看起来是需要新增一个router卡片，然后把业务作为子节点嵌入进去，然后build router重新更新。
                card_manager = self.card_handler.card_registry.get_manager(
                    CardConfigKeys.ROUTINE_RECORD
                ).record_card
                card_data = card_manager.build_record_card(
                    result.route_params.get("business_data", {})
                )

                self.user_service.save_new_card_business_data(
                    user_id, card_id, result.route_params.get("business_data", {})
                )

                self.sender.update_card_content(
                    card_id, card_data, sequence, message_id=card_message_id
                )
                self.cache_service.update_message_id_card_id_mapping(
                    card_message_id, card_id, "audio_stt_result"
                )
                self.cache_service.save_message_id_card_id_mapping()
                return

            # 这里既然没传输markdown_id以外的信息，就说明其实这里是需要重新组装business_data用于修改和储存
            business_data = self.user_service.get_card_business_data(user_id, card_id)
            if isinstance(result, Dict):
                # 用一个特别的分支返回处理的copletion，再在这里迭代更新试试看？
                # result就是business_data？
                # 有business_data作为数据容器，就不用action data里塞一堆了

                start_time = time.time()
                final_text = result["final_text"]
                user_input_markdown_element = JsonBuilder.build_markdown_element(
                    "**语音识别结果**"
                )

                # 这里的action_data意味着重新执行一次tts后续的步骤？也看情况，还是分个按钮好了。编辑之后有差异才显示。
                user_input_element = JsonBuilder.build_input_element(
                    "请输入你的想法",
                    final_text,
                    False,
                    {},
                    element_id="user_input",
                    input_type="multiline_text",
                )
                topic_info = result["domain_weights"]
                topic_match_thredhold = 50
                best_match_topic = max(topic_info, key=topic_info.get)
                if topic_info[best_match_topic] > topic_match_thredhold:
                    print("test-topic_info", topic_info, best_match_topic)
                else:
                    print("test-topic_info", topic_info)
                    best_match_topic = ""

                options_dict = {option: option for option in topic_info}
                options = JsonBuilder.build_options(options_dict)

                # 后来这里是要做一个多选和反选的逻辑的
                topic_domain_select_element = JsonBuilder.build_select_element(
                    "修改所属领域",
                    options,
                    best_match_topic,
                    False,
                    {},
                    element_id="topic_domain_select",
                )
                topic_row = JsonBuilder.build_form_row(
                    "相关领域",
                    topic_domain_select_element,
                    element_id="topic_row",
                )

                user_input_line_element = JsonBuilder.build_line_element()

                modify_button_element = JsonBuilder.build_button_element(
                    "润色",
                    element_id="input_button_0",
                )
                save_button_element = JsonBuilder.build_button_element(
                    "保存",
                    element_id="input_button_1",
                )
                input_button_group_element = JsonBuilder.build_button_group_element(
                    [modify_button_element, save_button_element]
                )

                new_elements = [
                    user_input_markdown_element,
                    user_input_element,
                    topic_row,
                    input_button_group_element,
                    user_input_line_element,
                ]

                self.sender.add_card_element(
                    card_id,
                    business_data.get("markdown_element_id", ""),
                    new_elements,
                    sequence,
                    add_position="insert_before",
                    message_id=card_message_id,
                    ignore_update_mapping=True,
                )

                role_1 = result["top_combinations"][0]

                blank_element = JsonBuilder.build_markdown_element(
                    "", element_id=business_data.get("markdown_element_id", "")
                )
                blank_element_json = json.dumps(blank_element, ensure_ascii=False)
                initial_text_element = False
                thought_animation_index = 0
                # 更新卡片元素，先清空，再更新，实现打字机效果
                ext_sequence = 0
                thought_text = ""
                tts_str = ""
                modified = False
                last_chunk = None
                for chunk in role_1["stream_completion"]:
                    last_chunk = chunk
                    if not chunk:
                        continue
                    for part in chunk.candidates[0].content.parts:
                        if not part.text:
                            continue
                        elif part.thought:
                            thought_animation_index = (
                                thought_animation_index + 1
                            ) % len(self.THOUGHT_ANIMATION)
                            thought_element = JsonBuilder.build_markdown_element(
                                self.THOUGHT_ANIMATION[thought_animation_index],
                                element_id=business_data.get("markdown_element_id", ""),
                            )
                            thought_element_json = json.dumps(
                                thought_element, ensure_ascii=False
                            )
                            ext_sequence += 1
                            self.sender.update_card_element(
                                card_id,
                                business_data.get("markdown_element_id", ""),
                                thought_element_json,
                                sequence + ext_sequence,
                            )
                            thought_text += part.text
                        else:
                            tts_str += part.text
                            if not initial_text_element:
                                initial_text_element = True
                                ext_sequence += 1
                                self.sender.update_card_element(
                                    card_id,
                                    business_data.get("markdown_element_id", ""),
                                    blank_element_json,
                                    sequence + ext_sequence,
                                )
                                ext_sequence += 1
                                final_text = (
                                    "来自" + role_1["identity"] + "身份的回复："
                                )
                                self.sender.stream_update_card_content(
                                    card_id,
                                    business_data.get("markdown_element_id", ""),
                                    final_text,
                                    sequence + ext_sequence,
                                )

                            final_text += part.text
                            ext_sequence += 1
                            self.sender.stream_update_card_content(
                                card_id,
                                business_data.get("markdown_element_id", ""),
                                final_text,
                                sequence + ext_sequence,
                            )
                            modified = True

                tts_result = self.message_router.media.process_tts_async(tts_str)
                if (
                    tts_result.success
                    and tts_result.response_type == ResponseTypes.AUDIO
                ):
                    audio_data = tts_result.response_content.get("audio_data")
                    if audio_data:
                        file_data = self.sender.upload_and_send_audio(
                            None, audio_data, return_mode="file"
                        )
                        if file_data:
                            file_key = file_data.get("file_key", "")
                            audio_element = JsonBuilder.build_audio_element(
                                file_key,
                                element_id=business_data.get(
                                    "audio_element_id", "audio_element_0"
                                ),
                                style="speak",
                                audio_id=business_data.get("audio_id", "audio_0"),
                            )
                            shift_button_element = JsonBuilder.build_button_element(
                                "换个角度",
                                size="small",
                                element_id="shift_button_0",
                            )
                            extra_button_element = JsonBuilder.build_button_element(
                                "展开说说",
                                size="small",
                                element_id="extra_button_0",
                            )
                            button_group_element = (
                                JsonBuilder.build_button_group_element(
                                    [shift_button_element, extra_button_element]
                                )
                            )
                            ext_sequence += 1
                            new_elements = [audio_element, button_group_element]

                            self.sender.add_card_element(
                                card_id,
                                business_data.get("markdown_element_id", ""),
                                new_elements,
                                sequence + ext_sequence,
                                message_id=card_message_id,
                                ignore_update_mapping=True,
                            )

                end_time = time.time()
                # if not modified:
                # if last_chunk.candidates[0].finish_reason != FinishReason.STOP:
                print("test-last_chunk", modified, last_chunk)
                print("test-thought_text\n", thought_text)
                if last_chunk is None:
                    print("启用第二套方案")
                    print("test- role1 detail", role_1["stream_completion"].__dict__())
                print(f"test-diff_completion_time: {round(end_time - start_time, 1)}s")
                ext_sequence += 1
                self.sender.finish_stream_card(
                    card_id, sequence + ext_sequence, "数字分身的回应"
                )
                self.cache_service.update_message_id_card_id_mapping(
                    card_message_id, card_id, "audio_stt_result"
                )
                self.cache_service.save_message_id_card_id_mapping()
                return

            if result.success and result.response_type == "text":
                # 发送STT结果

                blank_element = JsonBuilder.build_markdown_element(
                    "", element_id=business_data.get("markdown_element_id", "")
                )
                blank_element_json = json.dumps(blank_element, ensure_ascii=False)
                # 更新卡片元素，先清空，再更新，实现打字机效果
                self.sender.update_card_element(
                    card_id,
                    business_data.get("markdown_element_id", ""),
                    blank_element_json,
                    sequence,
                )

                self.sender.stream_update_card_content(
                    card_id,
                    business_data.get("markdown_element_id", ""),
                    result.response_content.get("text", "未获取到结果消息"),
                    sequence + 1,
                )
                # 完成流式卡片，关闭streaming_mode
                self.sender.finish_stream_card(card_id, sequence + 2, "贴心智能助手")
                self.cache_service.update_message_id_card_id_mapping(
                    card_message_id, card_id, "audio_stt_result"
                )
                self.cache_service.save_message_id_card_id_mapping()

            else:
                # STT处理失败，发送错误信息
                self.sender.send_feishu_message_reply(
                    context, result.response_content.get("text", "未获取到结果消息")
                )

        self._execute_async(process_in_background)

    # endregion

    # region 特殊格式结果回复

    def _handle_special_response_types(
        self, data, result, context, context_refactor
    ) -> bool:
        """处理特殊回复类型，返回True表示已处理"""
        if not result.success:
            return False

        response_type = result.response_type

        match response_type:
            case ResponseTypes.RICH_TEXT:
                self.sender.upload_and_send_rich_text(data, result)
                return True

            case ResponseTypes.IMAGE:
                image_data = result.response_content.get("image_data")
                if image_data:
                    self.sender.upload_and_send_single_image_data(data, image_data)
                else:
                    error_result = ProcessResult.error_result("图片数据为空")
                    self.sender.send_feishu_reply(data, error_result)
                return True

            case ResponseTypes.ADMIN_CARD_SEND:
                user_id = context.user_id
                chat_id = data.event.message.chat_id
                message_id = data.event.message.message_id
                operation_data = result.response_content
                operation_id = operation_data.get("operation_id", "")

                if self.card_handler:
                    # 发送管理员卡片
                    success, sent_message_id = (
                        self.card_handler._handle_admin_card_operation(
                            result_content=operation_data,
                            card_operation_type=CardOperationTypes.SEND,
                            chat_id=chat_id,
                            message_id=message_id,
                            user_id=user_id,
                        )
                    )
                else:
                    success, sent_message_id = False, None
                    debug_utils.log_and_print("❌ CardHandler未注入", log_level="ERROR")

                if success and sent_message_id and operation_id:
                    # 绑定操作ID和卡片消息ID
                    # 调用pending_cache_service绑定UI消息
                    if self.app_controller:
                        pending_cache_service = self.app_controller.get_service(
                            ServiceNames.PENDING_CACHE
                        )
                        if pending_cache_service:
                            bind_success = pending_cache_service.bind_ui_message(
                                operation_id, sent_message_id, UITypes.INTERACTIVE_CARD
                            )
                            if not bind_success:
                                debug_utils.log_and_print(
                                    f"❌ UI消息绑定失败: operation_id={operation_id}",
                                    log_level="ERROR",
                                )
                        else:
                            debug_utils.log_and_print(
                                "❌ pending_cache_service不可用", log_level="ERROR"
                            )
                    else:
                        debug_utils.log_and_print(
                            "❌ app_controller不可用", log_level="ERROR"
                        )

                if not success:
                    error_result = ProcessResult.error_result("管理员卡片发送失败")
                    self.sender.send_feishu_reply(
                        data, error_result, force_reply_mode="reply"
                    )
                return True

            case ResponseTypes.DESIGN_PLAN_CARD:
                # 设计方案卡片发送
                if self.card_handler:
                    self.card_handler.dispatch_card_response(
                        card_config_key="design_plan",
                        card_action="send_confirm_card",
                        result=result,
                        context_refactor=context_refactor,
                    )
                    return True

                return False

            case _:
                return False

    # endregion

    # region 辅助函数消息转换

    @message_conversion_safe("消息转换失败")
    def _convert_message_to_context(self, data) -> Optional[MessageContext]:
        """将飞书消息转换为标准消息上下文"""
        # 调试输出P2ImMessageReceiveV1对象信息
        self.debug_p2im_object(data, "P2ImMessageReceiveV1")
        self.debug_parent_id_analysis(data)

        # 提取基本信息
        event_id = data.header.event_id
        user_id = data.event.sender.sender_id.open_id

        # 提取通用数据（时间戳和用户名）
        user_name = self.sender.get_user_name(user_id)
        message_timestamp = extract_timestamp(data)

        # 提取消息特定内容
        message_type = data.event.message.message_type
        content = self._extract_message_content(data.event.message)
        content_refactor = self._extract_message_content_refactor(data.event.message)
        message_id = data.event.message.message_id
        parent_message_id = (
            data.event.message.parent_id
            if hasattr(data.event.message, "parent_id") and data.event.message.parent_id
            else None
        )

        New_MessageContext = MessageContext_Refactor(
            adapter_name=AdapterNames.FEISHU,
            timestamp=message_timestamp,
            event_id=event_id,
            user_id=user_id,
            user_name=user_name,
            message_id=message_id,
            parent_message_id=parent_message_id,
            message_type=message_type,
            content=content_refactor,
            metadata={
                "chat_id": data.event.message.chat_id,
                "chat_type": data.event.message.chat_type,
            },
        )

        legacy_context = MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=message_type,
            content=content,
            timestamp=message_timestamp,
            event_id=event_id,
            adapter_name=AdapterNames.FEISHU,
            message_id=message_id,
            parent_message_id=parent_message_id,
            metadata={
                "chat_id": data.event.message.chat_id,
                "chat_type": data.event.message.chat_type,
            },
        )

        return legacy_context, New_MessageContext

    def _parse_post_content(self, message) -> PostContent:
        """
        解析 POST 类型消息内容（统一解析逻辑）

        支持多语言格式：{"zh_cn": {...}, "en_us": {...}}
        支持简化格式：{"title": "...", "content": [...]}

        Args:
            message: 飞书消息对象

        Returns:
            PostContent: 解析后的 POST 内容
        """
        # 解析 JSON
        if isinstance(message.content, str):
            post_data = json.loads(message.content)
        else:
            post_data = message.content

        # 处理多语言结构：优先使用 zh_cn，否则使用第一个可用语言
        if "zh_cn" in post_data:
            lang_data = post_data["zh_cn"]
        elif "en_us" in post_data:
            lang_data = post_data["en_us"]
        elif "title" in post_data or "content" in post_data:
            # 简化格式，直接使用
            lang_data = post_data
        else:
            # 尝试获取第一个键的值
            lang_data = next(iter(post_data.values())) if post_data else {}

        # 提取 title 和 content
        title = lang_data.get("title", "")
        content_items = lang_data.get("content", [])

        # 合并所有文本内容和图片
        text_parts = []
        image_keys = []

        for item_group in content_items:
            if not isinstance(item_group, list):
                continue

            for item in item_group:
                if not isinstance(item, dict):
                    continue

                tag = item.get("tag")

                # 处理文本类型标签
                if tag == "text":
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)
                elif tag == "a":  # 超链接
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)
                elif tag == "at":  # @用户
                    # @标签通常不提取文本，但可以记录
                    pass
                elif tag == "md":  # Markdown
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)
                elif tag == "code_block":  # 代码块
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)

                # 处理图片类型标签
                elif tag == "img":
                    image_key = item.get("image_key")
                    if image_key:
                        image_keys.append(image_key)
                elif tag == "media":  # 视频（也包含封面图片）
                    image_key = item.get("image_key")
                    if image_key:
                        image_keys.append(image_key)

                # 其他标签（emotion, hr 等）忽略

        return PostContent(
            title=title,
            text=" ".join(text_parts),
            image_keys=image_keys,
            raw_content=post_data,
        )

    def _extract_message_content(self, message) -> Any:
        """提取飞书消息内容（legacy 方法）"""
        match message.message_type:
            case "text":
                return json.loads(message.content)["text"]
            case "image" | "audio":
                return json.loads(message.content)
            case "post":
                return self._parse_post_content(message)
            case _:
                return message.content

    def _extract_message_content_refactor(self, message) -> Any:
        """提取飞书消息内容（重构版，返回标准化数据类）"""
        match message.message_type:
            case "text":
                return TextContent(text=json.loads(message.content)["text"])
            case "image":
                return FileContent(image_key=json.loads(message.content)["image_key"])
            case "audio":
                return FileContent(file_key=json.loads(message.content)["file_key"])
            case "post":
                return self._parse_post_content(message)
            case _:
                return message.content

    # endregion
