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
import tempfile
import os
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

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
from .feishu_cards import initialize_card_managers, get_card_manager
from Module.Business.message_processor import MessageContext, ProcessResult
from .feishu_decorators import (
    feishu_event_handler_safe, message_conversion_safe, feishu_api_call,
    file_operation_safe, async_operation_safe, card_operation_safe
)

def custom_serializer(obj):
    """
    自定义序列化函数，用于json.dumps。
    它会尝试获取对象的__dict__，如果对象没有__dict__（例如内置类型或使用__slots__的对象），
    或者__dict__中的某些值无法直接序列化，则回退到str(obj)。
    """
    if isinstance(obj, bytes): # 处理字节串，例如图片内容
        return f"<bytes data len={len(obj)}>"
    if hasattr(obj, '__dict__'):
        # 创建一个新的字典，只包含非私有/保护的、非可调用属性
        # 并对每个值递归调用 custom_serializer
        return {
            k: custom_serializer(v)
            for k, v in vars(obj).items()
            if not k.startswith('_') # and not callable(v) # 通常SDK模型属性不是可调用的
        }
    elif isinstance(obj, list):
        return [custom_serializer(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(custom_serializer(item) for item in obj)
    elif isinstance(obj, dict):
        return {k: custom_serializer(v) for k, v in obj.items()}
    try:
        # 尝试让json自己处理，如果不行，则转为字符串
        json.dumps(obj) # 测试是否可序列化
        return obj
    except TypeError:
        return str(obj) # 对于无法序列化的，返回其字符串表示

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

        if not result.should_reply:
            return

        # 检查是否需要异步处理TTS
        if (result.success and
            result.response_content and
            result.response_content.get("next_action") == "process_tts"):

            tts_text = result.response_content.get("tts_text", "")
            self._handle_tts_async(data, tts_text)
            return

        # 检查是否需要异步处理图像生成
        if (result.success and
            result.response_content and
            result.response_content.get("next_action") == "process_image_generation"):

            prompt = result.response_content.get("generation_prompt", "")
            self._handle_image_generation_async(data, prompt)
            return

        # 检查是否需要异步处理图像转换
        if (result.success and
            result.response_content and
            result.response_content.get("next_action") == "process_image_conversion"):

            self._handle_image_conversion_async(data, context)
            return

        # 检查是否需要异步处理B站视频推荐
        if (result.success and
            result.response_content and
            result.response_content.get("next_action") == "process_bili_video"):

            user_id = result.response_content.get("user_id", "")
            if user_id:
                # 只有在有实际文本内容时才发送提示消息
                text_content = result.response_content.get("text", "")
                if text_content and text_content.strip():
                    self._send_feishu_reply(data, result)
                # 启动异步处理
                self._handle_bili_video_async(data, user_id)
                return

        # 检查是否是富文本类型
        if result.success and result.response_type == "rich_text":
            self._upload_and_send_rich_text(data, result)
            return

        # 检查是否需要发送管理员确认卡片
        if result.success and result.response_type == "admin_card_send":
            user_id = context.user_id
            success = self._handle_admin_card_operation(
                result.response_content,
                operation_type="send",
                user_id=user_id
            )
            if not success:
                # 发送失败，发送错误信息
                error_result = ProcessResult.error_result("管理员卡片发送失败")
                self._send_feishu_reply(data, error_result)
            return

        # 检查是否是单个图片类型
        if result.success and result.response_type == "image":
            image_data = result.response_content.get("image_data")
            image_name = result.response_content.get("image_name", "sample_image.jpg")
            if image_data:
                self._upload_and_send_single_image_data(data, image_data, image_name)
            else:
                error_result = ProcessResult.error_result("图片数据为空")
                self._send_feishu_reply(data, error_result)
            return

        # 发送结果
        self._send_feishu_reply(data, result)

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
                success = self._send_direct_message(context.user_id, result)

            self._handle_bili_video_async(data, user_id)
            return

        # 发送回复（菜单点击通常需要主动发送消息）
        if result.should_reply:
            success = self._send_direct_message(context.user_id, result)

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

        # 检查是否是B站卡片更新结果
        if result.success and result.response_type == "bili_card_update":
            # 使用统一的卡片处理方法
            return self._handle_bili_card_operation(
                result.response_content,
                operation_type="update_response",
                toast_message="视频成功设置为已读"
            )

        # 检查是否是管理员卡片更新结果
        if result.success and result.response_type == "admin_card_update":
            # 使用管理员卡片处理方法
            return self._handle_admin_card_operation(
                result.response_content,
                operation_type="update_response"
            )

        # 处理不同类型的响应
        if result.success:
            # 检查是否是卡片动作响应（包含卡片更新）
            if result.response_type == "card_action_response":
                # 返回原有格式的卡片更新响应
                response_data = result.response_content
                return P2CardActionTriggerResponse(response_data)
            else:
                # 普通成功响应
                return P2CardActionTriggerResponse({
                    "toast": {
                        "type": "success",
                        "content": "操作成功"
                    }
                })
        else:
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": result.error_message or "操作失败"
                }
            })

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
        # 使用卡片管理器构建卡片内容
        card_content = self.bili_card_manager.build_bili_video_menu_card(video_data)

        if operation_type == "send":
            # 发送新卡片
            user_id = kwargs.get("user_id")
            if not user_id:
                debug_utils.log_and_print("❌ 发送卡片缺少用户ID", log_level="ERROR")
                return False

            success = self._send_interactive_card(user_id, card_content)
            if not success:
                debug_utils.log_and_print("❌ B站视频卡片发送失败", log_level="ERROR")
            return success

        elif operation_type == "update_response":
            # 构建卡片更新响应
            toast_message = kwargs.get("toast_message", "操作成功")
            response_data = {
                "toast": {
                    "type": "success",
                    "content": toast_message
                },
                "card": {
                    "type": "raw",
                    "data": card_content
                }
            }
            return P2CardActionTriggerResponse(response_data)

        else:
            debug_utils.log_and_print(f"❌ 未知的卡片操作类型: {operation_type}", log_level="ERROR")
            return False

    @card_operation_safe("管理员卡片操作失败")
    def _handle_admin_card_operation(self, operation_data: Dict[str, Any], operation_type: str, **kwargs) -> Any:
        """
        统一处理管理员卡片的构建和操作

        Args:
            operation_data: 业务层返回的操作数据
            operation_type: 操作类型 ('send' | 'update_response')
            **kwargs: 额外参数(user_id, toast_message等)

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # 使用卡片管理器构建卡片内容
        card_content = self.admin_card_manager.build_user_update_confirm_card(operation_data)

        if operation_type == "send":
            # 发送新卡片
            user_id = kwargs.get("user_id")
            if not user_id:
                debug_utils.log_and_print("❌ 发送卡片缺少用户ID", log_level="ERROR")
                return False

            success = self._send_interactive_card(user_id, card_content)
            if not success:
                debug_utils.log_and_print("❌ 管理员卡片发送失败", log_level="ERROR")
            return success

        elif operation_type == "update_response":
            # 构建卡片更新响应
            toast_message = kwargs.get("toast_message", "操作完成")
            result_type = operation_data.get('result_type', 'success')

            # 根据结果类型设置Toast类型
            toast_type = result_type

            response_data = {
                "toast": {
                    "type": toast_type,
                    "content": toast_message
                },
                "card": {
                    "type": "raw",
                    "data": card_content
                }
            }
            return P2CardActionTriggerResponse(response_data)

        else:
            debug_utils.log_and_print(f"❌ 未知的管理员卡片操作类型: {operation_type}", log_level="ERROR")
            return False

    @message_conversion_safe("消息转换失败")
    def _convert_message_to_context(self, data) -> Optional[MessageContext]:
        """将飞书消息转换为标准消息上下文"""
        # 详细输出P2ImMessageReceiveV1对象信息
        debug_utils.log_and_print(f"🔍 P2ImMessageReceiveV1对象详细信息 (JSON序列化):", log_level="DEBUG")
        try:
            # 使用自定义序列化器进行转换
            serializable_data = custom_serializer(data)
            json_output = json.dumps(serializable_data, indent=2, ensure_ascii=False)
            debug_utils.log_and_print(json_output, log_level="DEBUG")
            debug_utils.log_and_print(f"🔍 P2ImMessageReceiveV1对象详细信息 (pprint):", log_level="DEBUG")
            dict_representation = custom_serializer(data)
            pretty_output = pprint.pformat(dict_representation, indent=2, width=120)
            debug_utils.log_and_print(pretty_output, log_level="DEBUG")
        except Exception as e:
            debug_utils.log_and_print(f"  - 序列化失败: {e}", log_level="ERROR")
            debug_utils.log_and_print(f"  - 尝试使用 repr(): {repr(data)}", log_level="DEBUG")

        # 特别关注回复消息的关键字段 parent_id
        if hasattr(data, 'event') and hasattr(data.event, 'message') and hasattr(data.event.message, 'parent_id'):
            parent_id = data.event.message.parent_id
            if parent_id:
                debug_utils.log_and_print(f"  - 关键信息: 此消息为回复消息, parent_id = {parent_id}", log_level="INFO")
            else:
                debug_utils.log_and_print(f"  - 关键信息: 此消息非回复消息 (parent_id is None or empty)", log_level="DEBUG")
        else:
            debug_utils.log_and_print(f"  - 关键信息: 未找到 parent_id 属性路径", log_level="DEBUG")
        # 提取基本信息
        event_id = data.header.event_id
        event_time = data.header.create_time or time.time()

        # 处理时间戳
        if isinstance(event_time, str):
            event_time = int(event_time)
        timestamp_seconds = int(event_time/1000) if event_time > 1e10 else int(event_time)
        timestamp = datetime.datetime.fromtimestamp(timestamp_seconds)

        # 提取用户信息
        user_id = data.event.sender.sender_id.open_id
        user_name = self._get_user_name(user_id)

        # 提取消息内容
        message_type = data.event.message.message_type
        content = self._extract_message_content(data.event.message)

        # 提取消息上下文信息
        message_id = data.event.message.message_id
        parent_message_id = data.event.message.parent_id if hasattr(data.event.message, 'parent_id') and data.event.message.parent_id else None

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=message_type,
            content=content,
            timestamp=timestamp,
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

    @message_conversion_safe("菜单转换失败")
    def _convert_menu_to_context(self, data) -> Optional[MessageContext]:
        """将飞书菜单点击转换为标准消息上下文"""
        # 提取基本信息
        event_id = data.header.event_id
        event_time = data.header.create_time or time.time()

        # 处理时间戳
        if isinstance(event_time, str):
            event_time = int(event_time)
        timestamp_seconds = int(event_time/1000) if event_time > 1e10 else int(event_time)
        timestamp = datetime.datetime.fromtimestamp(timestamp_seconds)

        # 提取用户信息
        user_id = data.event.operator.operator_id.open_id
        user_name = self._get_user_name(user_id)

        # 菜单事件的内容是event_key
        event_key = data.event.event_key

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type="menu_click",  # 自定义类型
            content=event_key,
            timestamp=timestamp,
            event_id=event_id,
            metadata={
                'app_id': data.header.app_id,
                'event_key': event_key,
                'interaction_type': 'menu'
            }
        )

    @message_conversion_safe("卡片转换失败")
    def _convert_card_to_context(self, data) -> Optional[MessageContext]:
        """将飞书卡片点击转换为标准消息上下文"""
        # 详细输出P2ImMessageReceiveV1对象信息
        debug_utils.log_and_print(f"🔍 P2ImMessageReceiveV1Card对象详细信息 (JSON序列化):", log_level="DEBUG")
        try:
            # 使用自定义序列化器进行转换
            serializable_data = custom_serializer(data)
            json_output = json.dumps(serializable_data, indent=2, ensure_ascii=False)
            debug_utils.log_and_print(json_output, log_level="DEBUG")
            debug_utils.log_and_print(f"🔍 P2ImMessageReceiveV1Card对象详细信息 (pprint):", log_level="DEBUG")
            dict_representation = custom_serializer(data)
            pretty_output = pprint.pformat(dict_representation, indent=2, width=120)
            debug_utils.log_and_print(pretty_output, log_level="DEBUG")
        except Exception as e:
            debug_utils.log_and_print(f"  - 序列化失败: {e}", log_level="ERROR")
            debug_utils.log_and_print(f"  - 尝试使用 repr(): {repr(data)}", log_level="DEBUG")

        # 提取基本信息
        event_id = f"card_{data.event.operator.open_id}_{int(time.time())}"  # 卡片事件生成ID
        timestamp = datetime.datetime.now()

        # 提取用户信息
        user_id = data.event.operator.open_id
        user_name = self._get_user_name(user_id)

        # 卡片动作信息
        action = data.event.action
        # 优化action.value为None或空的处理逻辑
        action_value = getattr(action, 'value', None)
        if not isinstance(action_value, dict) or action_value is None:
            action_value = {}

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type="card_action",  # 自定义类型
            content=action_value.get('action', 'unknown_action'),
            timestamp=timestamp,
            event_id=event_id,
            metadata={
                'action_value': action_value,
                'interaction_type': 'card',
                'open_message_id': data.event.context.open_message_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_message_id') else '',
                'open_chat_id': data.event.context.open_chat_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_chat_id') else ''
            }
        )

    def _extract_message_content(self, message) -> Any:
        """提取飞书消息内容"""
        if message.message_type == "text":
            return json.loads(message.content)["text"]
        elif message.message_type == "image":
            return json.loads(message.content)
        elif message.message_type == "audio":
            return json.loads(message.content)
        else:
            return message.content

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

    @feishu_api_call("发送飞书回复失败", return_value=False)
    def _send_feishu_reply(self, original_data, result: ProcessResult) -> bool:
        """
        发送飞书回复（统一的发送方法）

        Args:
            original_data: 原始飞书事件数据
            result: 处理结果（包含parent_id上下文信息）
        """
        if not result.response_content:
            return True

        # 转换响应内容为飞书格式
        content_json = json.dumps(result.response_content)

        # 根据parent_id决定回复方式
        if result.parent_id:
            # 业务层指定了要关联的消息ID，使用reply模式
            request = (
                ReplyMessageRequest.builder()
                .message_id(result.parent_id)  # 使用业务层指定的parent_id
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content_json)
                    .msg_type(result.response_type)
                    .build()
                )
                .build()
            )
            response = self.client.im.v1.message.reply(request)
        else:
            # 没有指定parent_id，使用默认逻辑（群聊reply，私聊新消息）
            if original_data.event.message.chat_type == "p2p":
                # 私聊：创建新消息
                request = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(original_data.event.message.chat_id)
                    .msg_type(result.response_type)
                    .content(content_json)
                    .build()
                ).build()
                response = self.client.im.v1.message.create(request)
            else:
                # 群聊：回复用户消息
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(original_data.event.message.message_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .content(content_json)
                        .msg_type(result.response_type)
                        .build()
                    )
                    .build()
                )
                response = self.client.im.v1.message.reply(request)

        if not response.success():
            debug_utils.log_and_print(
                f"飞书消息发送失败: {response.code} - {response.msg}",
                log_level="ERROR"
            )
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

    @file_operation_safe("发送交互式卡片失败", return_value=False)
    def _send_interactive_card(self, user_id: str, card_content: Dict[str, Any]) -> bool:
        """发送交互式卡片消息"""
        # 将卡片内容转换为JSON字符串
        content_json = json.dumps(card_content, ensure_ascii=False)
        # print('test-card_content',type(card_content), user_id,'\n', content_json)
        # final_output_string = json.dumps(content_json, ensure_ascii=False)
        # print('test-card_content',type(content_json), user_id,'\n', final_output_string)

        # 创建发送请求
        request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(user_id)
            .msg_type("interactive")
            .content(content_json)
            .build()
        ).build()

        response = self.client.im.v1.message.create(request)

        if not response.success():
            debug_utils.log_and_print(
                f"飞书交互式卡片发送失败: {response.code} - {response.msg}",
                log_level="ERROR"
            )
            return False

        return True

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
        content_data = "{\"data\": {\"template_id\": \"AAqBPdq4sxIy5\", \"template_variable\": {\"main_title\": \"【官方MV】大石昌良 - uni-verse《古力特宇宙》主题曲\", \"main_pageid\": \"21536d82-1893-8158-b64b-e89a231ee457\", \"main_priority\": \"👾低\", \"main_duration_str\": \"4分30秒\", \"main_author\": \"大石昌良\", \"main_source\": \"主页推送\", \"main_upload_date_str\": \"2025-06-16\", \"main_summary\": \"感受《古力特宇宙》主题曲的魅力，体验动画与音乐的完美融合。\", \"main_url\": \"https://www.bilibili.com/video/BV1HqNbzEEHp?adskip=none\", \"main_android_url\": \"bilibili://video/BV1HqNbzEEHp\", \"main_is_read_str\": \"\", \"main_is_read\": false, \"action_info\": {\"action\": \"mark_bili_read\", \"pageid\": \"21536d82-1893-8158-b64b-e89a231ee457\", \"card_type\": \"menu\", \"cached_video_data\": {\"main_video\": {\"title\": \"【官方MV】大石昌良 - uni-verse《古力特宇宙》主题曲\", \"url\": \"https://www.bilibili.com/video/BV1HqNbzEEHp?adskip=none\", \"pageid\": \"21536d82-1893-8158-b64b-e89a231ee457\", \"success\": true, \"author\": \"大石昌良\", \"duration_str\": \"4分30秒\", \"chinese_priority\": \"👾低\", \"chinese_source\": \"主页推送\", \"summary\": \"感受《古力特宇宙》主题曲的魅力，体验动画与音乐的完美融合。\", \"upload_date\": \"2025-06-16\", \"is_read\": false, \"is_read_str\": \"\", \"android_url\": \"bilibili://video/BV1HqNbzEEHp\"}, \"additional_videos\": [{\"title\": \"炒面技巧是要表面脆，面芯软《豉油王炒面》\", \"url\": \"https://www.bilibili.com/video/BV1iMNbzMEGV?adskip=none\", \"pageid\": \"21536d82-1893-8182-be78-de5f47832705\", \"duration_str\": \"12分钟\", \"author\": \"酒满饭宝\", \"chinese_priority\": \"👾低\", \"chinese_source\": \"主页推送\", \"is_read\": false, \"is_read_str\": \"\", \"android_url\": \"bilibili://video/BV1iMNbzMEGV\"}]}, \"video_index\": 0}, \"addtional_videos\": [{\"title\": \"炒面技巧是要表面脆，面芯软《豉油王炒面》\", \"pageid\": \"21536d82-1893-8182-be78-de5f47832705\", \"priority\": \"👾低\", \"duration_str\": \"12分钟\", \"video_index\": \"1\", \"is_read_str\": \"\", \"is_read\": false, \"url\": \"https://www.bilibili.com/video/BV1iMNbzMEGV?adskip=none\", \"android_url\": \"bilibili://video/BV1iMNbzMEGV\", \"action_info\": {\"action\": \"mark_bili_read\", \"pageid\": \"21536d82-1893-8158-b64b-e89a231ee457\", \"card_type\": \"menu\", \"cached_video_data\": {\"main_video\": {\"title\": \"【官方MV】大石昌良 - uni-verse《古力特宇宙》主题曲\", \"url\": \"https://www.bilibili.com/video/BV1HqNbzEEHp?adskip=none\", \"pageid\": \"21536d82-1893-8158-b64b-e89a231ee457\", \"success\": true, \"author\": \"大石昌良\", \"duration_str\": \"4分30秒\", \"chinese_priority\": \"👾低\", \"chinese_source\": \"主页推送\", \"summary\": \"感受《古力特宇宙》主题曲的魅力，体验动画与音乐的完美融合。\", \"upload_date\": \"2025-06-16\", \"is_read\": false, \"is_read_str\": \"\", \"android_url\": \"bilibili://video/BV1HqNbzEEHp\"}, \"additional_videos\": [{\"title\": \"炒面技巧是要表面脆，面芯软《豉油王炒面》\", \"url\": \"https://www.bilibili.com/video/BV1iMNbzMEGV?adskip=none\", \"pageid\": \"21536d82-1893-8182-be78-de5f47832705\", \"duration_str\": \"12分钟\", \"author\": \"酒满饭宝\", \"chinese_priority\": \"👾低\", \"chinese_source\": \"主页推送\", \"is_read\": false, \"is_read_str\": \"\", \"android_url\": \"bilibili://video/BV1iMNbzMEGV\"}]}, \"video_index\": 1}}]}, \"template_version_name\": \"1.0.6\"}, \"type\": \"template\"}"

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

        # 在新线程中处理
        import threading
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

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

        # 在新线程中处理
        import threading
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

    @async_operation_safe("图像转换异步处理失败")
    def _handle_image_conversion_async(self, original_data, context):
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

        # 在新线程中处理
        import threading
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

    @async_operation_safe("B站视频推荐异步处理失败")
    def _handle_bili_video_async(self, original_data, user_id: str):
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

        # 在新线程中处理
        import threading
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

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
        import base64
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
        else:
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
                image_content = json.dumps({"image_key": upload_response.data.image_key})
                image_result = ProcessResult.success_result("image", {"image_key": upload_response.data.image_key}, parent_id=original_data.event.message.message_id)
                return self._send_feishu_reply(original_data, image_result)
            else:
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
            else:
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
            else:
                debug_utils.log_and_print(
                    f"音频上传失败: {upload_response.code} - {upload_response.msg}",
                    log_level="ERROR"
                )
                return None

    @file_operation_safe("富文本上传发送失败", return_value=False)
    def _upload_and_send_rich_text(self, original_data, result: ProcessResult) -> bool:
        """上传并发送富文本"""
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody
        from io import BytesIO

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
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody
        from io import BytesIO

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