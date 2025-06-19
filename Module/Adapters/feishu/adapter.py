"""
飞书适配器 - 处理飞书平台特定的协议转换

该模块职责：
1. 飞书WebSocket连接管理
2. 飞书消息格式与标准格式的双向转换
3. 飞书特定的API调用
"""

import json
import time
import datetime
import os
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
from io import BytesIO
import base64
import threading

import pprint
import lark_oapi as lark
from lark_oapi.api.contact.v3 import GetUserRequest
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, CreateMessageRequestBody,
    ReplyMessageRequest, ReplyMessageRequestBody,
    CreateFileRequest, CreateFileRequestBody,
    GetMessageResourceRequest,
    CreateImageRequest, CreateImageRequestBody,
    PatchMessageRequest, PatchMessageRequestBody
)
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

from Module.Common.scripts.common import debug_utils
from .cards import initialize_card_managers, get_card_manager
from Module.Business.message_processor import MessageContext, ProcessResult
from .decorators import (
    feishu_event_handler_safe, message_conversion_safe, feishu_api_call,
    file_operation_safe, async_operation_safe, card_operation_safe, feishu_sdk_safe
)

# P2ImMessageReceiveV1对象调试开关 - 开发调试用
DEBUG_P2IM_OBJECTS = False  # 设置为True启用详细调试输出


def custom_serializer(obj):
    """
    自定义序列化函数，用于json.dumps。
    它会尝试获取对象的__dict__，如果对象没有__dict__（例如内置类型或使用__slots__的对象），
    或者__dict__中的某些值无法直接序列化，则回退到str(obj)。
    """
    # 处理特殊类型
    if isinstance(obj, bytes):
        return f"<bytes data len={len(obj)}>"

    # 处理复合类型
    if isinstance(obj, (list, tuple)):
        return [custom_serializer(item) for item in obj]

    if isinstance(obj, dict):
        return {k: custom_serializer(v) for k, v in obj.items()}

    # 处理有__dict__的对象
    if hasattr(obj, '__dict__'):
        return {
            k: custom_serializer(v)
            for k, v in vars(obj).items()
            if not k.startswith('_')
        }

    # 尝试JSON序列化，失败则转为字符串
    try:
        json.dumps(obj)  # 测试是否可序列化
        return obj
    except TypeError:
        return str(obj)


def debug_p2im_object(data, object_type: str = "P2ImMessageReceiveV1"):
    """
    调试P2ImMessageReceiveV1对象的详细信息输出

    Args:
        data: 需要调试的对象
        object_type: 对象类型名称（用于日志标识）
    """
    if not DEBUG_P2IM_OBJECTS:
        return

    debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (JSON序列化):", log_level="DEBUG")
    try:
        # 使用自定义序列化器进行转换
        serializable_data = custom_serializer(data)
        json_output = json.dumps(serializable_data, indent=2, ensure_ascii=False)
        debug_utils.log_and_print(json_output, log_level="DEBUG")
        debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (pprint):", log_level="DEBUG")
        dict_representation = custom_serializer(data)
        pretty_output = pprint.pformat(dict_representation, indent=2, width=120)
        debug_utils.log_and_print(pretty_output, log_level="DEBUG")
    except Exception as e:
        debug_utils.log_and_print(f"  - 序列化失败: {e}", log_level="ERROR")
        debug_utils.log_and_print(f"  - 尝试使用 repr(): {repr(data)}", log_level="DEBUG")


def debug_parent_id_analysis(data):
    """
    分析并调试parent_id相关信息

    Args:
        data: 需要分析的消息对象
    """
    if not DEBUG_P2IM_OBJECTS:
        return

    # 特别关注回复消息的关键字段 parent_id
    if hasattr(data, 'event') and hasattr(data.event, 'message') and hasattr(data.event.message, 'parent_id'):
        parent_id = data.event.message.parent_id
        if parent_id:
            debug_utils.log_and_print(f"  - 关键信息: 此消息为回复消息, parent_id = {parent_id}", log_level="INFO")
        else:
            debug_utils.log_and_print("  - 关键信息: 此消息非回复消息 (parent_id is None or empty)", log_level="DEBUG")
    else:
        debug_utils.log_and_print("  - 关键信息: 未找到 parent_id 属性路径", log_level="DEBUG")


class FeishuAdapter:
    """
    飞书平台适配器

    职责：纯粹的协议转换和平台接口封装
    不包含任何业务逻辑，只负责与飞书平台的交互

    支持的交互类型：
    - 消息交互 (文本、图片、音频)
    - 菜单交互 (机器人菜单点击)
    - 卡片交互 (卡片按钮点击)

    回复模式控制：
    - 业务层通过parent_id指定回复关系，适配器根据parent_id决定发送方式
    - 有parent_id: 使用reply模式，关联到指定的消息
    - 无parent_id: 群聊默认reply用户消息，私聊创建新消息
    """

    def __init__(self, message_processor, app_controller=None):
        """
        初始化飞书适配器

        Args:
            message_processor: 消息处理器实例
            app_controller: 应用控制器，用于获取配置
        """
        self.message_processor = message_processor
        self.app_controller = app_controller

        # 导入并初始化新的卡片管理架构
        self.card_registry = initialize_card_managers()
        self.bili_card_manager = get_card_manager("bilibili")
        self.admin_card_manager = get_card_manager("admin")

        # 初始化飞书SDK配置
        self._init_feishu_config()

        # 创建飞书客户端
        self.client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()

        # 创建WebSocket客户端
        self.ws_client = self._create_ws_client()

    def _init_feishu_config(self):
        """初始化飞书配置"""
        if self.app_controller:
            # 从配置服务获取
            success, app_id = self.app_controller.call_service('config', 'get', 'FEISHU_APP_MESSAGE_ID')
            success2, app_secret = self.app_controller.call_service('config', 'get', 'FEISHU_APP_MESSAGE_SECRET')
            success3, log_level_str = self.app_controller.call_service('config', 'get', 'log_level', 'INFO')

            self.app_id = app_id if success else os.getenv("FEISHU_APP_MESSAGE_ID", "")
            self.app_secret = app_secret if success2 else os.getenv("FEISHU_APP_MESSAGE_SECRET", "")
            self.log_level = getattr(lark.LogLevel, log_level_str) if success3 else lark.LogLevel.INFO
        else:
            # 从环境变量获取
            self.app_id = os.getenv("FEISHU_APP_MESSAGE_ID", "")
            self.app_secret = os.getenv("FEISHU_APP_MESSAGE_SECRET", "")
            self.log_level = lark.LogLevel.INFO

        # 设置全局配置
        lark.APP_ID = self.app_id
        lark.APP_SECRET = self.app_secret

    def _create_ws_client(self):
        """创建WebSocket客户端"""
        # 创建事件处理器
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_feishu_message)
            .register_p2_application_bot_menu_v6(self._handle_feishu_menu)
            .register_p2_card_action_trigger(self._handle_feishu_card)
            .build()
        )

        # 创建WebSocket客户端
        return lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=self.log_level
        )

    # ================ 通用工具方法 ================

    def _execute_async(self, func):
        """通用异步执行方法，统一管理线程创建"""
        thread = threading.Thread(target=func)
        thread.daemon = True
        thread.start()

    def _extract_common_context_data(self, data, user_id: str) -> Dict[str, Any]:
        """
        提取消息上下文的通用数据

        Args:
            data: 飞书事件数据
            user_id: 用户ID

        Returns:
            Dict: 包含timestamp和user_name的字典
        """
        # 提取并处理时间戳
        event_time = data.header.create_time or time.time()
        if isinstance(event_time, str):
            event_time = int(event_time)
        timestamp_seconds = int(event_time/1000) if event_time > 1e10 else int(event_time)
        timestamp = datetime.datetime.fromtimestamp(timestamp_seconds)

        # 获取用户名
        user_name = self._get_user_name(user_id)

        return {
            'timestamp': timestamp,
            'user_name': user_name
        }

    @feishu_api_call("获取用户名失败", return_value="用户_未知")
    def _get_user_name(self, open_id: str) -> str:
        """获取用户名称"""
        # 先从缓存获取
        if self.app_controller:
            success, cached_name = self.app_controller.call_service('cache', 'get', f"user:{open_id}")
            if success and cached_name:
                return cached_name

        # 从飞书API获取
        request = GetUserRequest.builder().user_id_type("open_id").user_id(open_id).build()
        response = self.client.contact.v3.user.get(request)
        if response.success() and response.data and response.data.user:
            name = response.data.user.name
            # 缓存用户名
            if self.app_controller:
                self.app_controller.call_service('cache', 'set', f"user:{open_id}", name, 604800)
            return name

        return f"用户_{open_id[:8]}"

    # ================ 事件处理方法（消息类型）================

    @feishu_event_handler_safe("处理飞书消息失败")
    def _handle_feishu_message(self, data) -> None:
        """
        处理飞书消息事件

        这是飞书SDK的回调函数，负责：
        1. 将飞书消息转换为标准格式
        2. 调用业务处理器
        3. 将处理结果转换为飞书消息发送
        """
        # 转换为标准消息上下文
        context = self._convert_message_to_context(data)
        if context is None:
            debug_utils.log_and_print("消息上下文转换失败", log_level="ERROR")
            return

        # 调用业务处理器
        result = self.message_processor.process_message(context)

        # 不需要回复的情况
        if not result.should_reply:
            return

        # 处理异步操作
        if self._handle_async_actions(data, result):
            return

        # 处理特殊回复类型
        if self._handle_special_response_types(data, result, context):
            return

        # 默认发送普通回复
        self._send_feishu_reply(data, result)

    def _handle_async_actions(self, data, result) -> bool:
        """处理异步操作，返回True表示已处理"""
        if not (result.success and result.response_content):
            return False

        next_action = result.response_content.get("next_action")
        if not next_action:
            return False

        # 异步操作映射表，直接映射到处理逻辑
        action_handlers = {
            "process_tts": lambda: self._handle_tts_async(data, result.response_content.get("tts_text", "")),
            "process_image_generation": lambda: self._handle_image_generation_async(data, result.response_content.get("generation_prompt", "")),
            "process_image_conversion": lambda: self._handle_image_conversion_async(data),
            "process_bili_video": lambda: self._handle_bili_video_with_text_check(data, result)
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
                self._send_feishu_reply(data, result)
            self._handle_bili_video_async(user_id)


    @async_operation_safe("TTS异步处理失败")
    def _handle_tts_async(self, original_data, tts_text: str):
        """异步处理TTS请求"""
        def process_in_background():
            # 调用业务处理器的异步TTS方法
            result = self.message_processor.process_tts_async(tts_text)

            if result.success and result.response_type == "audio":
                # 上传并发送音频
                audio_data = result.response_content.get("audio_data")
                if audio_data:
                    self._upload_and_send_audio(original_data, audio_data)
                else:
                    # 音频数据为空，发送错误提示
                    error_result = ProcessResult.error_result("音频生成失败，数据为空")
                    self._send_feishu_reply(original_data, error_result)
            else:
                # TTS处理失败，发送错误信息
                self._send_feishu_reply(original_data, result)

        # 使用通用异步执行方法
        self._execute_async(process_in_background)

    @async_operation_safe("图像生成异步处理失败")
    def _handle_image_generation_async(self, original_data, prompt: str):
        """异步处理图像生成请求"""
        def process_in_background():
            # 先发送处理中提示
            processing_result = ProcessResult.success_result("text", {"text": "正在生成图片，请稍候..."})
            self._send_feishu_reply(original_data, processing_result)

            # 调用业务处理器的异步图像生成方法
            result = self.message_processor.process_image_generation_async(prompt)

            if result.success and result.response_type == "image_list":
                # 上传并发送图像
                image_paths = result.response_content.get("image_paths", [])
                if image_paths:
                    self._upload_and_send_images(original_data, image_paths)
                else:
                    # 图像列表为空，发送错误提示
                    error_result = ProcessResult.error_result("图像生成失败，结果为空")
                    self._send_feishu_reply(original_data, error_result)
            else:
                # 图像生成失败，发送错误信息
                self._send_feishu_reply(original_data, result)

        # 使用通用异步执行方法
        self._execute_async(process_in_background)

    @async_operation_safe("图像转换异步处理失败")
    def _handle_image_conversion_async(self, original_data):
        """异步处理图像转换请求"""
        def process_in_background():
            # 先发送处理中提示
            processing_result = ProcessResult.success_result("text", {"text": "正在转换图片风格，请稍候..."})
            self._send_feishu_reply(original_data, processing_result)

            # 获取图像资源
            image_data = self._get_image_resource(original_data)
            if not image_data:
                error_result = ProcessResult.error_result("获取图片资源失败")
                self._send_feishu_reply(original_data, error_result)
                return

            image_base64, mime_type, file_name, file_size = image_data

            # 调用业务处理器的异步图像转换方法
            result = self.message_processor.process_image_conversion_async(
                image_base64, mime_type, file_name, file_size
            )

            if result.success and result.response_type == "image_list":
                # 上传并发送图像
                image_paths = result.response_content.get("image_paths", [])
                if image_paths:
                    self._upload_and_send_images(original_data, image_paths)
                else:
                    # 图像列表为空，发送错误提示
                    error_result = ProcessResult.error_result("图像转换失败，结果为空")
                    self._send_feishu_reply(original_data, error_result)
            else:
                # 图像转换失败，发送错误信息
                self._send_feishu_reply(original_data, result)

        # 使用通用异步执行方法
        self._execute_async(process_in_background)

    @async_operation_safe("B站视频推荐异步处理失败")
    def _handle_bili_video_async(self, user_id: str):
        """异步处理B站视频推荐请求（使用新的卡片架构）"""

        def process_in_background():
            # 调用业务处理器获取原始数据
            result = self.message_processor.process_bili_video_async()

            if result.success and result.response_type == "bili_video_data":
                # 使用统一的卡片处理方法
                success = self._handle_bili_card_operation(
                    result.response_content,
                    operation_type="send",
                    user_id=user_id
                )

                if not success:
                    # 发送失败，使用降级方案
                    error_result = ProcessResult.error_result("B站视频卡片发送失败")
                    self._send_direct_message(user_id, error_result)
            else:
                debug_utils.log_and_print(f"❌ B站视频获取失败: {result.error_message}", log_level="ERROR")
                # B站视频获取失败，发送错误信息
                self._send_direct_message(user_id, result)

        # 使用通用异步执行方法
        self._execute_async(process_in_background)


    def _handle_special_response_types(self, data, result, context) -> bool:
        """处理特殊回复类型，返回True表示已处理"""
        if not result.success:
            return False

        match result.response_type:
            case "rich_text":
                self._upload_and_send_rich_text(data, result)
                return True

            case "admin_card_send":
                user_id = context.user_id
                chat_id = data.event.message.chat_id
                message_id = data.event.message.message_id
                success = self._handle_admin_card_operation(
                    result.response_content,
                    operation_type="send",
                    user_id=user_id,
                    chat_id=chat_id,
                    message_id=message_id
                )
                if not success:
                    error_result = ProcessResult.error_result("管理员卡片发送失败")
                    self._send_feishu_reply(data, error_result, force_reply_mode="reply")
                return True

            case "image":
                image_data = result.response_content.get("image_data")
                image_name = result.response_content.get("image_name", "sample_image.jpg")
                if image_data:
                    self._upload_and_send_single_image_data(data, image_data, image_name)
                else:
                    error_result = ProcessResult.error_result("图片数据为空")
                    self._send_feishu_reply(data, error_result)
                return True

            case _:
                return False

    @message_conversion_safe("消息转换失败")
    def _convert_message_to_context(self, data) -> Optional[MessageContext]:
        """将飞书消息转换为标准消息上下文"""
        # 调试输出P2ImMessageReceiveV1对象信息
        debug_p2im_object(data, "P2ImMessageReceiveV1")
        debug_parent_id_analysis(data)

        # 提取基本信息
        event_id = data.header.event_id
        user_id = data.event.sender.sender_id.open_id

        # 提取通用数据（时间戳和用户名）
        common_data = self._extract_common_context_data(data, user_id)

        # 提取消息特定内容
        message_type = data.event.message.message_type
        content = self._extract_message_content(data.event.message)
        message_id = data.event.message.message_id
        parent_message_id = data.event.message.parent_id if hasattr(data.event.message, 'parent_id') and data.event.message.parent_id else None

        return MessageContext(
            user_id=user_id,
            user_name=common_data['user_name'],
            message_type=message_type,
            content=content,
            timestamp=common_data['timestamp'],
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

    # ================ 事件处理方法（菜单类型）================

    @feishu_event_handler_safe("飞书菜单处理失败")
    def _handle_feishu_menu(self, data) -> None:
        """
        处理飞书菜单点击事件

        将菜单点击转换为标准消息上下文处理
        """
        # 转换为标准消息上下文
        context = self._convert_menu_to_context(data)
        if not context:
            debug_utils.log_and_print("❌ 菜单上下文转换失败", log_level="ERROR")
            return

        # 调用业务处理器
        result = self.message_processor.process_message(context)

        # 检查是否需要异步处理B站视频推荐
        if (result.success and
            result.response_content and
            result.response_content.get("next_action") == "process_bili_video"):

            user_id = result.response_content.get("user_id", "")

            # 只有在有实际文本内容时才发送提示消息
            text_content = result.response_content.get("text", "")
            if text_content and text_content.strip():
                self._send_direct_message(context.user_id, result)

            self._handle_bili_video_async(user_id)
            return

        # 发送回复（菜单点击通常需要主动发送消息）
        if result.should_reply:
            self._send_direct_message(context.user_id, result)

    @message_conversion_safe("菜单转换失败")
    def _convert_menu_to_context(self, data) -> Optional[MessageContext]:
        """将飞书菜单点击转换为标准消息上下文"""
        # 提取基本信息
        event_id = data.header.event_id
        user_id = data.event.operator.operator_id.open_id

        # 提取通用数据（时间戳和用户名）
        common_data = self._extract_common_context_data(data, user_id)

        # 菜单事件的内容是event_key
        event_key = data.event.event_key

        return MessageContext(
            user_id=user_id,
            user_name=common_data['user_name'],
            message_type="menu_click",  # 自定义类型
            content=event_key,
            timestamp=common_data['timestamp'],
            event_id=event_id,
            metadata={
                'app_id': data.header.app_id,
                'event_key': event_key,
                'interaction_type': 'menu'
            }
        )

    # ================ 事件处理方法（卡片类型）================

    @card_operation_safe("飞书卡片处理失败")
    def _handle_feishu_card(self, data) -> P2CardActionTriggerResponse:
        """
        处理飞书卡片按钮点击事件

        将卡片点击转换为标准消息上下文处理
        """
        # 转换为标准消息上下文
        context = self._convert_card_to_context(data)
        if not context:
            return P2CardActionTriggerResponse({})

        # 调用业务处理器，由业务层判断处理类型
        result = self.message_processor.process_message(context)

        # 统一处理成功和失败的响应，减少分支嵌套
        if result.success:
            # 特殊类型处理
            match result.response_type:
                case "bili_card_update":
                    return self._handle_bili_card_operation(
                        result.response_content,
                        operation_type="update_response",
                        toast_message="视频成功设置为已读"
                    )
                case "admin_card_update":
                    return self._handle_admin_card_operation(
                        result.response_content,
                        operation_type="update_response"
                    )
                case "card_action_response":
                    return P2CardActionTriggerResponse(result.response_content)
                case _:
                    # 默认成功响应
                    return P2CardActionTriggerResponse({
                        "toast": {
                            "type": "success",
                            "content": "操作成功"
                        }
                    })
        else:
            # 失败响应
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": result.error_message or "操作失败"
                }
            })

    @message_conversion_safe("卡片转换失败")
    def _convert_card_to_context(self, data) -> Optional[MessageContext]:
        """将飞书卡片点击转换为标准消息上下文"""
        # 调试输出P2ImMessageReceiveV1Card对象信息
        debug_p2im_object(data, "P2ImMessageReceiveV1Card")

        # 提取基本信息
        event_id = f"card_{data.event.operator.open_id}_{int(time.time())}"  # 卡片事件生成ID
        user_id = data.event.operator.open_id

        # 对于卡片事件，使用当前时间而不是事件时间（保持原有逻辑）
        timestamp = datetime.datetime.now()
        user_name = self._get_user_name(user_id)

        # 卡片动作信息
        action = data.event.action
        # 优化action.value为None或空的处理逻辑
        action_value = getattr(action, 'value', None)
        if not isinstance(action_value, dict) or action_value is None:
            action_value = {}

        action_tag = action.tag if hasattr(action, 'tag') else 'button'

        # 处理select_static类型的特殊情况
        if action_tag == 'select_static':
            # 对于select_static，action.option包含选中的值
            action_option = action.option if hasattr(action, 'option') else '0'
            action_value.update({
                'action': 'select_change',  # 统一的动作名
                'option': action_option,
                'tag': action_tag
            })
            content = 'select_change'
        else:
            # 普通按钮动作
            content = action_value.get('action', 'unknown_action')

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type="card_action",  # 自定义类型
            content=content,
            timestamp=timestamp,
            event_id=event_id,
            metadata={
                'action_value': action_value,
                'action_tag': action_tag,
                'interaction_type': 'card',
                'open_message_id': data.event.context.open_message_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_message_id') else '',
                'open_chat_id': data.event.context.open_chat_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_chat_id') else ''
            }
        )

    @card_operation_safe("B站卡片操作失败")
    def _handle_bili_card_operation(self, video_data: Dict[str, Any], operation_type: str, **kwargs) -> Any:
        """
        统一处理B站卡片的构建和操作

        Args:
            video_data: 业务层返回的视频数据
            operation_type: 操作类型 ('send' | 'update_response')
            **kwargs: 额外参数(user_id, toast_message等)

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # B站特有的参数验证
        if operation_type == "send":
            user_id = kwargs.get("user_id")
            if not user_id:
                debug_utils.log_and_print("❌ 发送B站卡片缺少用户ID", log_level="ERROR")
                return False

        # 使用通用卡片操作处理
        return self._handle_card_operation_common(
            card_manager=self.bili_card_manager,
            build_method_name="build_bili_video_menu_card",
            data=video_data,
            operation_type=operation_type,
            card_config_type="bilibili_cards",
            **kwargs
        )

    @card_operation_safe("管理员卡片操作失败")
    def _handle_admin_card_operation(self, operation_data: Dict[str, Any], operation_type: str, **kwargs) -> Any:
        """
        统一处理管理员卡片的构建和操作

        Args:
            operation_data: 业务层返回的操作数据
            operation_type: 操作类型 ('send' | 'update_response')
            **kwargs: 额外参数(chat_id, user_id, message_id等)

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # 管理员特有的参数验证
        if operation_type == "send":
            chat_id = kwargs.get("chat_id")
            message_id = kwargs.get("message_id")
            if not chat_id or not message_id:
                debug_utils.log_and_print("❌ 发送管理员卡片缺少chat_id或message_id", log_level="ERROR")
                return False

        # 使用通用卡片操作处理
        return self._handle_card_operation_common(
            card_manager=self.admin_card_manager,
            build_method_name="build_user_update_confirm_card",
            data=operation_data,
            operation_type=operation_type,
            card_config_type="admin_cards",
            **kwargs
        )

    def _handle_card_operation_common(
        self,
        card_manager,
        build_method_name: str,
        data: Dict[str, Any],
        operation_type: str,
        card_config_type: str,
        **kwargs
    ) -> Any:
        """
        通用卡片操作处理方法

        Args:
            card_manager: 卡片管理器实例
            build_method_name: 卡片构建方法名
            data: 业务数据
            operation_type: 操作类型 ('send' | 'update_response')
            card_config_type: 卡片配置类型，用于获取回复模式
            **kwargs: 额外参数

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # 使用卡片管理器构建卡片内容
        build_method = getattr(card_manager, build_method_name)
        card_content = build_method(data)

        match operation_type:
            case "send":
                # 从配置获取卡片的回复模式
                reply_mode = self._get_card_reply_mode(card_config_type)

                # 构建发送参数
                send_params = {"card_content": card_content, "reply_mode": reply_mode}
                send_params.update(kwargs)

                success = self._send_interactive_card(**send_params)
                if not success:
                    debug_utils.log_and_print(f"❌ {card_config_type}卡片发送失败", log_level="ERROR")
                return success

            case "update_response":
                # 构建卡片更新响应
                toast_message = kwargs.get("toast_message", "操作完成")
                result_type = data.get('result_type', 'success') if isinstance(data, dict) else 'success'

                response_data = {
                    "toast": {
                        "type": result_type,
                        "content": toast_message
                    },
                    "card": {
                        "type": "raw",
                        "data": card_content
                    }
                }
                return P2CardActionTriggerResponse(response_data)

            case _:
                debug_utils.log_and_print(f"❌ 未知的{card_config_type}卡片操作类型: {operation_type}", log_level="ERROR")
                return False

    @feishu_sdk_safe("获取卡片回复模式失败", return_value="reply")
    def _get_card_reply_mode(self, card_type: str) -> str:
        """
        从配置获取卡片回复模式

        Args:
            card_type: 卡片类型 ("admin_cards" | "bilibili_cards" | 等)

        Returns:
            str: 回复模式 ("new" | "reply" | "thread")
        """
        config_service = self.app_controller.get_service('config') if self.app_controller else None
        if config_service:
            reply_modes = config_service.get("cards", {}).get("reply_modes", {})
            return reply_modes.get(card_type, reply_modes.get("default", "reply"))

        debug_utils.log_and_print("⚠️ 无法获取配置服务，使用默认回复模式", log_level="WARNING")
        return "reply"

    @feishu_api_call("发送飞书回复失败", return_value=False)
    def _send_feishu_reply(self, original_data, result: ProcessResult, force_reply_mode: str = None) -> bool:
        """
        发送飞书回复消息

        支持3种消息模式：
        1. "new" - 新消息 (CreateMessage)
        2. "reply" - 回复消息 (ReplyMessage)
        3. "thread" - 回复新话题 (ReplyMessage + reply_in_thread)

        Args:
            original_data: 原始飞书消息数据
            result: 处理结果
            force_reply_mode: 强制指定回复模式 ("new"|"reply"|"thread")
        """
        if not result.should_reply:
            return True

        # 转换响应内容为飞书格式
        content_json = json.dumps(result.response_content)

        # 决定消息模式
        reply_mode = self._determine_reply_mode(original_data, result, force_reply_mode)

        # 提取基础信息
        chat_id = original_data.event.message.chat_id
        user_id = original_data.event.sender.sender_id.open_id

        try:
            match reply_mode:
                case "new":
                    # 模式1: 新消息
                    return self._send_create_message(user_id, content_json, result.response_type)

                case "reply" | "thread":
                    # 模式2&3: 回复消息 (含新话题)
                    message_id = original_data.event.message.message_id
                    return self._send_reply_message(message_id, content_json, result.response_type, reply_mode == "thread")

                case _:
                    debug_utils.log_and_print(f"❌ 未知的回复模式: {reply_mode}", log_level="ERROR")
                    return False

        except Exception as e:
            debug_utils.log_and_print(f"❌ 发送消息失败: {e}", log_level="ERROR")
            return False

    def _determine_reply_mode(self, original_data, result: ProcessResult, force_mode: str = None) -> str:
        """
        决定回复模式

        优先级:
        1. 强制模式参数
        2. ProcessResult中的parent_id指定
        3. 消息类型和聊天类型的默认策略
        """
        if force_mode in ["new", "reply", "thread"]:
            return force_mode

        # 根据parent_id判断
        if result.parent_id:
            return "reply"

        # 默认策略: 群聊回复，私聊新消息
        chat_type = original_data.event.message.chat_type
        return "reply" if chat_type == "group" else "new"

    def _send_create_message(self, user_id: str, content: str, msg_type: str) -> bool:
        """发送新消息"""
        request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(user_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        ).build()

        response = self.client.im.v1.message.create(request)
        if not response.success():
            debug_utils.log_and_print(f"❌ 新消息发送失败: {response.code} - {response.msg}", log_level="ERROR")
            return False
        return True

    def _send_reply_message(self, message_id: str, content: str, msg_type: str, reply_in_thread: bool = False) -> bool:
        """发送回复消息"""
        builder = ReplyMessageRequestBody.builder() \
            .msg_type(msg_type) \
            .content(content)

        if reply_in_thread:
            builder = builder.reply_in_thread(True)

        request = ReplyMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(builder.build()) \
            .build()

        response = self.client.im.v1.message.reply(request)
        if not response.success():
            debug_utils.log_and_print(f"❌ 回复消息发送失败: {response.code} - {response.msg}", log_level="ERROR")
            return False
        return True

    @feishu_api_call("发送飞书直接消息失败", return_value=False)
    def _send_direct_message(self, user_id: str, result: ProcessResult) -> bool:
        """发送直接消息（用于菜单点击等主动发送）"""
        if not result.response_content:
            return True

        # 转换响应内容为飞书格式
        content_json = json.dumps(result.response_content)

        # 直接发送给用户
        request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(user_id)
            .msg_type(result.response_type)
            .content(content_json)
            .build()
        ).build()
        response = self.client.im.v1.message.create(request)

        if not response.success():
            debug_utils.log_and_print(
                f"飞书直接消息发送失败: {response.code} - {response.msg}",
                log_level="ERROR"
            )
            return False

        return True

    @feishu_api_call("发送交互式卡片失败", return_value=False)
    def _send_interactive_card(
        self,
        chat_id: str = None,
        user_id: str = None,
        card_content: Dict[str, Any] = None,
        reply_mode: str = "new",
        message_id: str = None
    ) -> bool:
        """
        统一的交互式卡片发送方法

        支持3种发送模式：
        1. "new" - 新消息模式 (CreateMessage)
        2. "reply" - 回复模式 (ReplyMessage)
        3. "thread" - 回复新话题模式 (ReplyMessage + reply_in_thread)

        Args:
            chat_id: 聊天ID (new模式使用)
            user_id: 用户ID (new模式的替代方案，兼容旧版本)
            card_content: 卡片内容
            reply_mode: 发送模式 ("new"|"reply"|"thread")
            message_id: 回复的消息ID (reply/thread模式必需)

        Returns:
            bool: 是否发送成功
        """
        # 参数验证
        validation_result = self._validate_card_send_params(
            card_content, reply_mode, chat_id, user_id, message_id
        )
        if not validation_result["valid"]:
            debug_utils.log_and_print(f"❌ {validation_result['error']}", log_level="ERROR")
            return False

        # 将卡片内容转换为JSON字符串
        content_json = json.dumps(card_content, ensure_ascii=False)

        # 处理不同发送模式
        match reply_mode:
            case "reply" | "thread":
                # 复用_send_reply_message逻辑，统一处理
                return self._send_reply_message(
                    message_id=message_id,
                    content=content_json,
                    msg_type="interactive",
                    reply_in_thread=(reply_mode == "thread")
                )

            case "new":
                # 处理新消息模式
                return self._send_new_interactive_card(chat_id, user_id, content_json)

            case _:
                debug_utils.log_and_print(f"❌ 不支持的发送模式: {reply_mode}", log_level="ERROR")
                return False

    def _validate_card_send_params(
        self, card_content, reply_mode: str, chat_id: str, user_id: str, message_id: str
    ) -> Dict[str, Any]:
        """验证卡片发送参数"""
        if not card_content:
            return {"valid": False, "error": "卡片内容为空"}

        match reply_mode:
            case "new":
                if not (chat_id or user_id):
                    return {"valid": False, "error": "新消息模式需要chat_id或user_id"}

            case "reply" | "thread":
                if not message_id:
                    return {"valid": False, "error": "回复模式需要message_id"}

            case _:
                return {"valid": False, "error": f"不支持的发送模式: {reply_mode}"}

        return {"valid": True}

    @feishu_api_call("发送新交互式卡片失败", return_value=False)
    def _send_new_interactive_card(self, chat_id: str, user_id: str, content_json: str) -> bool:
        """发送新的交互式卡片消息"""
        # 确定接收者信息
        receive_id = chat_id or user_id
        receive_id_type = "chat_id" if chat_id else "open_id"

        # 构建请求
        request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("interactive")
            .content(content_json)
            .build()
        ).build()

        # 发送请求
        response = self.client.im.v1.message.create(request)

        if response.success():
            debug_utils.log_and_print("✅ 交互式卡片发送成功 (模式:new)", log_level="INFO")
            return True

        debug_utils.log_and_print(
            f"❌ 交互式卡片发送失败 (模式:new): {response.code} - {response.msg}",
            log_level="ERROR"
        )
        return False

    @file_operation_safe("获取图像资源失败", return_value=None)
    def _get_image_resource(self, original_data) -> Optional[Tuple[str, str, str, int]]:
        """
        获取图像资源

        Returns:
            Optional[Tuple[str, str, str, int]]: (base64图像数据, MIME类型, 文件名, 文件大小)
        """
        message = original_data.event.message
        image_content = json.loads(message.content)

        if "image_key" not in image_content:
            debug_utils.log_and_print("图片消息格式错误，缺少image_key", log_level="ERROR")
            return None

        image_key = image_content["image_key"]
        message_id = message.message_id

        # 获取图片资源
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(image_key) \
            .type("image") \
            .build()

        response = self.client.im.v1.message_resource.get(request)

        if not response.success():
            debug_utils.log_and_print(f"获取图片资源失败: {response.code} - {response.msg}", log_level="ERROR")
            return None

        # 读取图片数据
        file_content = response.file.read()
        if not file_content:
            debug_utils.log_and_print("图片数据为空", log_level="ERROR")
            return None

        # 获取文件信息
        file_name = getattr(response.file, "file_name", "image.jpg")
        mime_type = getattr(response.file, "content_type", "image/jpeg")
        file_size = len(file_content)

        # 转换为base64
        image_base64 = base64.b64encode(file_content).decode('utf-8')

        debug_utils.log_and_print(f"成功获取图片资源: {file_name}, 大小: {file_size} bytes", log_level="INFO")
        return image_base64, mime_type, file_name, file_size

    @file_operation_safe("批量上传图片失败", return_value=False)
    def _upload_and_send_images(self, original_data, image_paths: List[str]) -> bool:
        """上传并发送多张图片"""
        success_count = 0

        for image_path in image_paths:
            if not image_path or not os.path.exists(image_path):
                continue

            # 上传单张图片
            if self._upload_and_send_single_image(original_data, image_path):
                success_count += 1

        if success_count > 0:
            debug_utils.log_and_print(f"成功发送 {success_count}/{len(image_paths)} 张图片", log_level="INFO")
            return True

        debug_utils.log_and_print("没有成功发送任何图片", log_level="ERROR")
        return False

    @file_operation_safe("上传单张图片失败", return_value=False)
    def _upload_and_send_single_image(self, original_data, image_path: str) -> bool:
        """上传并发送单张图片"""
        with open(image_path, "rb") as image_file:
            upload_response = self.client.im.v1.image.create(
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(image_file)
                    .build()
                )
                .build()
            )

            if (upload_response.success() and
                upload_response.data and
                upload_response.data.image_key):

                # 发送图片消息
                image_result = ProcessResult.success_result("image", {"image_key": upload_response.data.image_key}, parent_id=original_data.event.message.message_id)
                return self._send_feishu_reply(original_data, image_result)

            debug_utils.log_and_print(f"图片上传失败: {upload_response.code} - {upload_response.msg}", log_level="ERROR")
            return False

    @file_operation_safe("音频上传处理失败", return_value=False)
    def _upload_and_send_audio(self, original_data, audio_data: bytes) -> bool:
        """上传音频并发送消息"""
        temp_mp3_path = None
        temp_opus_path = None

        try:
            # 获取音频服务
            if not self.app_controller:
                debug_utils.log_and_print("应用控制器不可用", log_level="ERROR")
                return False

            audio_service = self.app_controller.get_service('audio')
            if not audio_service:
                debug_utils.log_and_print("音频服务不可用", log_level="ERROR")
                return False

            # 创建临时MP3文件
            temp_mp3_path = audio_service.create_temp_audio_file(audio_data, ".mp3")

            # 转换为opus格式
            temp_opus_path, duration_ms = audio_service.convert_to_opus(temp_mp3_path)

            if not temp_opus_path or not os.path.exists(temp_opus_path):
                debug_utils.log_and_print("音频转换失败", log_level="ERROR")
                return False

            # 上传到飞书
            file_key = self._upload_opus_to_feishu(temp_opus_path, duration_ms)

            if file_key:
                # 发送音频消息
                content_json = json.dumps({"file_key": file_key})
                result = ProcessResult.success_result("audio", json.loads(content_json), parent_id=original_data.event.message.message_id)
                return self._send_feishu_reply(original_data, result)

            debug_utils.log_and_print("音频上传到飞书失败", log_level="ERROR")
            return False

        finally:
            # 清理临时文件
            if temp_mp3_path and audio_service:
                audio_service.cleanup_temp_file(temp_mp3_path)
            if temp_opus_path and audio_service:
                audio_service.cleanup_temp_file(temp_opus_path)

    @file_operation_safe("音频上传异常", return_value=None)
    def _upload_opus_to_feishu(self, opus_path: str, duration_ms: int) -> Optional[str]:
        """上传opus音频文件到飞书"""
        with open(opus_path, "rb") as audio_file:
            opus_filename = Path(opus_path).name

            upload_response = self.client.im.v1.file.create(
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type("opus")
                    .file_name(opus_filename)
                    .duration(str(int(duration_ms)))
                    .file(audio_file)
                    .build()
                ).build()
            )

            if upload_response.success() and upload_response.data and upload_response.data.file_key:
                return upload_response.data.file_key

            debug_utils.log_and_print(
                f"音频上传失败: {upload_response.code} - {upload_response.msg}",
                log_level="ERROR"
            )
            return None

    @file_operation_safe("富文本上传发送失败", return_value=False)
    def _upload_and_send_rich_text(self, original_data, result: ProcessResult) -> bool:
        """上传并发送富文本"""

        # 上传示例图片
        image_data = result.response_content.get("sample_image_data")
        if not image_data:
            # 如果没有图片数据，发送纯文本富文本
            rich_text_content = result.response_content.get("rich_text_content")
            result = ProcessResult.success_result("post", rich_text_content, parent_id=result.parent_id)
            return self._send_feishu_reply(original_data, result)

        # 上传图片
        image_file = BytesIO(image_data)
        upload_response = self.client.im.v1.image.create(
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image_file)
                .build()
            )
            .build()
        )

        if not (upload_response.success() and upload_response.data and upload_response.data.image_key):
            debug_utils.log_and_print("富文本图片上传失败", log_level="ERROR")
            return False

        # 在富文本内容中添加图片
        rich_text_content = result.response_content.get("rich_text_content")
        image_key = upload_response.data.image_key

        # 在第二行插入图片（在链接行后面）
        rich_text_content["zh_cn"]["content"].insert(1, [{"tag": "img", "image_key": image_key}])

        # 使用统一的发送方法
        result = ProcessResult.success_result("post", rich_text_content, parent_id=result.parent_id)
        return self._send_feishu_reply(original_data, result)

    @file_operation_safe("示例图片上传发送失败", return_value=False)
    def _upload_and_send_single_image_data(self, original_data, image_data: bytes, image_name: str) -> bool:
        """上传并发送单个图片（从内存数据）"""
        image_file = BytesIO(image_data)
        upload_response = self.client.im.v1.image.create(
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image_file)
                .build()
            )
            .build()
        )

        if not (upload_response.success() and upload_response.data and upload_response.data.image_key):
            debug_utils.log_and_print(f"图片上传失败: {image_name}", log_level="ERROR")
            return False

        # 使用统一的发送方法
        image_key = upload_response.data.image_key
        result = ProcessResult.success_result("image", {"image_key": image_key}, parent_id=original_data.event.message.message_id)
        success = self._send_feishu_reply(original_data, result)

        if success:
            debug_utils.log_and_print(f"示例图片发送成功: {image_name}", log_level="INFO")

        return success

    def start(self):
        """启动飞书WebSocket连接（同步方式）"""
        debug_utils.log_and_print("启动飞书适配器 (同步模式)", log_level="INFO")
        self.ws_client.start()

    async def start_async(self):
        """启动飞书WebSocket连接（异步方式）"""
        debug_utils.log_and_print("启动飞书适配器 (异步模式)", log_level="INFO")
        await self.ws_client._connect()

    def stop(self):
        """停止飞书WebSocket连接"""
        if hasattr(self, 'ws_client') and self.ws_client:
            try:
                self.ws_client.close()
            except:
                pass

    def get_status(self) -> Dict[str, Any]:
        """获取适配器状态"""
        return {
            "adapter_type": "FeishuAdapter",
            "app_id": self.app_id[:10] + "..." if len(self.app_id) > 10 else self.app_id,
            "log_level": self.log_level.name if hasattr(self.log_level, 'name') else str(self.log_level),
            "message_processor_available": self.message_processor is not None,
            "supported_interactions": ["message", "menu", "card"]
        }

    # ================ 备份无法触发更新卡片的Patch方法，待后续更新================

    @file_operation_safe("更新交互式卡片失败", return_value=False)
    def _update_interactive_card(self, message_id: str, card_content: Dict[str, Any]) -> bool:
        """更新交互式卡片消息"""
        # 将卡片内容转换为JSON字符串
        content_json = json.dumps(card_content, ensure_ascii=False)
        # print('test-card_content',type(card_content), message_id,'\n', content_json)
        # final_output_string = json.dumps(content_json, ensure_ascii=False, indent=2, sort_keys=True)
        # print('test-card_content',type(content_json), message_id,'\n', final_output_string)

        # # 创建更新请求
        # request = PatchMessageRequest.builder() \
        #     .message_id(message_id) \
        #     .request_body(PatchMessageRequestBody.builder()
        #         .content(content_json)
        #         .build()) \
        #     .build()

        # 两次json dump的结果贴在这里
        content_data = "{\"data\": {\"templatete\"}"

        temp_client = lark.Client.builder() \
            .app_id("cli_a6bf8e1105de900b") \
            .app_secret("MlKGGQOiMhz9KSl3e05DObSff5GvgcqL") \
            .log_level(lark.LogLevel.DEBUG) \
            .build()
        # 构造请求对象
        request: PatchMessageRequest = PatchMessageRequest.builder() \
            .message_id("om_x100b4a15be28a1700f247d7b26d0720") \
            .request_body(PatchMessageRequestBody.builder()
                .content(content_data)
                .build()) \
            .build()

        # response = self.client.im.v1.message.patch(request)
        response = temp_client.im.v1.message.patch(request)

        if not response.success():
            debug_utils.log_and_print(
                f"飞书交互式卡片更新失败: {response.code} - {response.msg}",
                log_level="ERROR"
            )
            return False

        debug_utils.log_and_print("✅ 交互式卡片更新成功", log_level="INFO")
        return True
