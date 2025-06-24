"""
飞书消息处理器 (Feishu Message Handler)

负责处理飞书消息事件，包括：
- 消息接收和转换
- 异步操作处理
- 特殊响应类型处理
"""

import json
import datetime
import threading
from typing import Optional, Dict, Any

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import MessageContext, ProcessResult
from ..decorators import (
    feishu_event_handler_safe, message_conversion_safe, async_operation_safe
)
from ..utils import extract_timestamp, noop_debug
from Module.Services.constants import (
    ServiceNames, UITypes, ResponseTypes, Messages, CardOperationTypes, ProcessResultConstKeys, ProcessResultNextAction
)


class MessageHandler:
    """飞书消息处理器"""

    def __init__(self, message_processor, sender, user_name_getter, debug_functions=None):
        """
        初始化消息处理器

        Args:
            message_processor: 业务消息处理器
            sender: 消息发送器实例
            user_name_getter: 用户名获取函数
            debug_functions: 调试函数字典，包含debug_p2im_object等
        """
        self.message_processor = message_processor
        self.sender = sender
        self._get_user_name = user_name_getter

        # 获取应用控制器以访问服务
        self.app_controller = getattr(message_processor, 'app_controller', None)
        self.debug_p2im_object = debug_functions.get('debug_p2im_object', noop_debug)
        self.debug_parent_id_analysis = debug_functions.get('debug_parent_id_analysis', noop_debug)
        self.card_handler = None  # 将由adapter注入

    @property
    def card_mapping_service(self):
        """获取卡片业务映射服务"""
        if self.app_controller:
            return self.app_controller.get_service(ServiceNames.CARD_BUSINESS_MAPPING)
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
        """
        # 转换为标准消息上下文
        context = self._convert_message_to_context(data)
        if not context:
            debug_utils.log_and_print("❌ 消息上下文转换失败", log_level="ERROR")
            return

        # 调用业务处理器
        result = self.message_processor.process_message(context)

        # 检查是否需要异步处理
        if self._handle_async_actions(data, result):
            return

        # 检查特殊响应类型
        if self._handle_special_response_types(data, result, context):
            return

        # 普通回复
        if result.should_reply:
            self.sender.send_feishu_reply(data, result)

    def _handle_async_actions(self, data, result) -> bool:
        """处理异步操作，返回True表示已处理"""
        if not (result.success and result.response_content):
            return False

        next_action = result.response_content.get(ProcessResultConstKeys.NEXT_ACTION)
        if not next_action:
            return False

        # 异步操作映射表，直接映射到处理逻辑
        action_handlers = {
            ProcessResultNextAction.PROCESS_TTS: lambda: self._handle_tts_async(data, result.response_content.get("tts_text", "")),
            ProcessResultNextAction.PROCESS_IMAGE_GENERATION: lambda: self._handle_image_generation_async(data, result.response_content.get("generation_prompt", "")),
            ProcessResultNextAction.PROCESS_IMAGE_CONVERSION: lambda: self._handle_image_conversion_async(data),
            ProcessResultNextAction.PROCESS_BILI_VIDEO: lambda: self._handle_bili_video_with_text_check(data, result)
        }

        handler = action_handlers.get(next_action)
        if handler:
            handler()
            return True

        return False

    def _handle_bili_video_with_text_check(self, data, result):
        """处理B站视频操作（包含文本检查逻辑）"""
        user_id = result.response_content.get("user_id", "")
        if user_id:
            text_content = result.response_content.get("text", "")
            if text_content and text_content.strip():
                self.sender.send_feishu_reply(data, result)
            self._handle_bili_video_async(user_id)

    @async_operation_safe("TTS异步处理失败")
    def _handle_tts_async(self, original_data, tts_text: str):
        """异步处理TTS任务"""
        def process_in_background():
            # 调用业务处理器的异步TTS方法
            result = self.message_processor.media.process_tts_async(tts_text)

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
            result = self.message_processor.media.process_image_generation_async(prompt)

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
            result = self.message_processor.media.process_image_conversion_async(
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

    @async_operation_safe("B站视频推荐异步处理失败")
    def _handle_bili_video_async(self, user_id: str):
        """异步处理B站视频推荐任务"""
        def process_in_background():
            # 调用业务处理器获取原始数据
            result = self.message_processor.bili.process_bili_video_async()

            if result.success and result.response_type == ResponseTypes.BILI_VIDEO_DATA:
                if self.card_handler:
                    success = self.card_handler._handle_bili_card_operation(
                        result.response_content,
                        card_operation_type=CardOperationTypes.SEND,
                        user_id=user_id
                    )
                else:
                    success = False
                    debug_utils.log_and_print("❌ CardHandler未注入", log_level="ERROR")

                if not success:
                    # 发送失败，使用降级方案
                    error_result = ProcessResult.error_result("B站视频卡片发送失败")
                    self.sender.send_direct_message(user_id, error_result)
            else:
                debug_utils.log_and_print(f"❌ B站视频获取失败: {result.error_message}", log_level="ERROR")
                # B站视频获取失败，发送错误信息
                self.sender.send_direct_message(user_id, result)

        self._execute_async(process_in_background)

    def _handle_special_response_types(self, data, result, context) -> bool:
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
                        operation_data=operation_data,
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
        message_id = data.event.message.message_id
        parent_message_id = data.event.message.parent_id if hasattr(data.event.message, 'parent_id') and data.event.message.parent_id else None

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=message_type,
            content=content,
            timestamp=message_timestamp,
            event_id=event_id,
            message_id=message_id,
            parent_message_id=parent_message_id,
            metadata={
                'chat_id': data.event.message.chat_id,
                'message_id': message_id,
                'chat_type': data.event.message.chat_type,
                'interaction_type': 'message'
            }
        )

    def _extract_message_content(self, message) -> Any:
        """提取飞书消息内容"""
        match message.message_type:
            case "text":
                return json.loads(message.content)["text"]
            case "image" | "audio":
                return json.loads(message.content)
            case _:
                return message.content


