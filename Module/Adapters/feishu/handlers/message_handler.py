"""
飞书消息处理器 (Feishu Message Handler)

负责处理飞书消息事件，包括：
- 消息接收和转换
- 异步操作处理
- 特殊响应类型处理
"""

import json
import threading
from typing import Optional, Dict, Any

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import (
    MessageContext, ProcessResult, MessageContext_Refactor,
    TextContent, FileContent
)
from ..decorators import (
    feishu_event_handler_safe, message_conversion_safe, async_operation_safe
)
from ..utils import extract_timestamp, noop_debug
from Module.Services.constants import (
    ServiceNames, UITypes, ResponseTypes, Messages, CardOperationTypes, ProcessResultConstKeys, ProcessResultNextAction, AdapterNames
)


class MessageHandler:
    """飞书消息处理器"""

    def __init__(self, message_router, sender, user_name_getter, debug_functions=None):
        """
        初始化消息处理器

        Args:
            message_router: 业务消息路由器
            sender: 消息发送器实例
            user_name_getter: 用户名获取函数
            debug_functions: 调试函数字典，包含debug_p2im_object等
        """
        self.message_router = message_router
        self.sender = sender
        self._get_user_name = user_name_getter

        # 获取应用控制器以访问服务
        self.app_controller = getattr(message_router, 'app_controller', None)
        self.debug_p2im_object = debug_functions.get('debug_p2im_object', noop_debug)
        self.debug_parent_id_analysis = debug_functions.get('debug_parent_id_analysis', noop_debug)
        self.card_handler = None  # 将由adapter注入

    @property
    def card_mapping_service(self):
        """获取卡片业务映射服务"""
        if self.app_controller:
            return self.app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        return None

    def set_card_handler(self, card_handler):
        """注入CardHandler实例"""
        self.card_handler = card_handler


    def _execute_async(self, func):
        """执行异步操作的通用方法"""
        thread = threading.Thread(target=func)
        thread.daemon = True
        thread.start()

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

        # 调用业务处理器
        result = self.message_router.process_message(context)

        # 检查是否需要异步处理
        if self._handle_async_actions(data, result, context_refactor):
            return

        # 检查特殊响应类型
        if self._handle_special_response_types(data, result, context, context_refactor):
            return

        # 普通回复
        if result.should_reply:
            self.sender.send_feishu_reply(data, result)

    def _handle_async_actions(self, data, result: ProcessResult, context_refactor: MessageContext_Refactor) -> bool:
        """处理异步操作，返回True表示已处理"""

        # 异步操作映射表，直接映射到处理逻辑——后续要换成配置
        action_handlers = {
            ProcessResultNextAction.PROCESS_TTS: lambda: self._handle_tts_async(data, result.response_content.get("tts_text", "")),
            ProcessResultNextAction.PROCESS_IMAGE_GENERATION: lambda: self._handle_image_generation_async(data, result.response_content.get("generation_prompt", "")),
            ProcessResultNextAction.PROCESS_IMAGE_CONVERSION: lambda: self._handle_image_conversion_async(data),
            ProcessResultNextAction.PROCESS_BILI_VIDEO: lambda: self._handle_bili_video_async(context_refactor)
        }

        if result.response_type == ResponseTypes.ASYNC_ACTION:
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

    @async_operation_safe("B站视频推荐异步处理失败")
    def _handle_bili_video_async(self, context_refactor: MessageContext_Refactor):
        """异步处理B站视频推荐任务"""
        def process_in_background():
            # 调用业务处理器获取原始数据
            result = self.message_router.bili.process_bili_video_async()

            if self.card_handler:
                self.card_handler.dispatch_card_response(
                    card_config_key="bilibili_video_info",
                    card_action="send_video_card",
                    result=result,
                    context_refactor=context_refactor
                )
            else:
                debug_utils.log_and_print("❌ CardHandler未注入", log_level="ERROR")
                self.sender.send_direct_message(context_refactor.user_id, result)

        self._execute_async(process_in_background)

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
            processing_result = ProcessResult.success_result(ResponseTypes.TEXT, {"text": Messages.IMAGE_GENERATING})
            self.sender.send_feishu_reply(original_data, processing_result)

            # 调用业务处理器的异步图像生成方法
            result = self.message_router.media.process_image_generation_async(prompt)

            if result.success and result.response_type == ResponseTypes.IMAGE_LIST:
                # 上传并发送图像
                image_paths = result.response_content.get("image_paths", [])
                if image_paths:
                    self.sender.upload_and_send_images(original_data, image_paths)
                else:
                    # 图像列表为空，发送错误提示
                    error_result = ProcessResult.error_result("图像生成失败，结果为空")
                    self.sender.send_feishu_reply(original_data, error_result)
            else:
                # 图像生成失败，发送错误信息
                self.sender.send_feishu_reply(original_data, result)

        self._execute_async(process_in_background)

    @async_operation_safe("图像转换异步处理失败")
    def _handle_image_conversion_async(self, original_data):
        """异步处理图像转换任务"""
        def process_in_background():
            # 先发送处理中提示
            processing_result = ProcessResult.success_result("text", {"text": "正在转换图片风格，请稍候..."})
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

    def _handle_special_response_types(self, data, result, context, context_refactor) -> bool:
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
                operation_id = operation_data.get('operation_id', '')

                if self.card_handler:
                    # 发送管理员卡片
                    success, sent_message_id = self.card_handler._handle_admin_card_operation(
                        result_content=operation_data,
                        card_operation_type=CardOperationTypes.SEND,
                        chat_id=chat_id,
                        message_id=message_id
                    )
                else:
                    success, sent_message_id = False, None
                    debug_utils.log_and_print("❌ CardHandler未注入", log_level="ERROR")

                if success and sent_message_id and operation_id:
                    # 绑定操作ID和卡片消息ID
                    # 调用pending_cache_service绑定UI消息
                    if self.app_controller:
                        pending_cache_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)
                        if pending_cache_service:
                            bind_success = pending_cache_service.bind_ui_message(operation_id, sent_message_id, UITypes.INTERACTIVE_CARD)
                            if not bind_success:
                                debug_utils.log_and_print(f"❌ UI消息绑定失败: operation_id={operation_id}", log_level="ERROR")
                        else:
                            debug_utils.log_and_print("❌ pending_cache_service不可用", log_level="ERROR")
                    else:
                        debug_utils.log_and_print("❌ app_controller不可用", log_level="ERROR")

                if not success:
                    error_result = ProcessResult.error_result("管理员卡片发送失败")
                    self.sender.send_feishu_reply(data, error_result, force_reply_mode="reply")
                return True

            case ResponseTypes.DESIGN_PLAN_CARD:
                # 设计方案卡片发送
                if self.card_handler:
                    self.card_handler.dispatch_card_response(
                        card_config_key="design_plan",
                        card_action="send_confirm_card",
                        result=result,
                        context_refactor=context_refactor
                    )
                    return True

                return False

            case _:
                return False

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
        user_name = self._get_user_name(user_id)
        message_timestamp = extract_timestamp(data)

        # 提取消息特定内容
        message_type = data.event.message.message_type
        content = self._extract_message_content(data.event.message)
        content_refactor = self._extract_message_content_refactor(data.event.message)
        message_id = data.event.message.message_id
        parent_message_id = data.event.message.parent_id if hasattr(data.event.message, 'parent_id') and data.event.message.parent_id else None

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
                'chat_id': data.event.message.chat_id,
                'chat_type': data.event.message.chat_type
            }
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
                'chat_id': data.event.message.chat_id,
                'chat_type': data.event.message.chat_type
            }
        )

        return legacy_context, New_MessageContext

    def _extract_message_content(self, message) -> Any:
        """提取飞书消息内容"""
        match message.message_type:
            case "text":
                return json.loads(message.content)["text"]
            case "image" | "audio":
                return json.loads(message.content)
            case _:
                return message.content


    def _extract_message_content_refactor(self, message) -> Any:
        """提取飞书消息内容"""
        match message.message_type:
            case "text":
                return TextContent(text=json.loads(message.content)["text"])
            case "image":
                return FileContent(image_key=json.loads(message.content)["image_key"])
            case "audio":
                return FileContent(file_key=json.loads(message.content)["file_key"])
            case _:
                return message.content



