"""
飞书消息处理模块

该模块实现了飞书平台的消息处理
"""

from io import BytesIO
import json
import os
from typing import Any, Optional
import asyncio

from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateFileRequest,
    CreateFileRequestBody,
    GetMessageResourceRequest,
)

from Module.Interface.message import Message, MessageType, MessageHandler, MessageResponse
from Module.Common.scripts.common import debug_utils
from Module.Platforms.feishu.action_handlers import ActionHandlerFactory


class FeishuMessageHandler(MessageHandler):
    """飞书消息处理实现"""

    def __init__(self, client, bot_service=None):
        """
        初始化飞书消息处理

        Args:
            client: 飞书客户端
            bot_service: 机器人服务
        """
        self.client = client
        self.bot_service = bot_service

    def parse_bot_menu_click(self, platform_message: Any) -> Message:
        """
        解析飞书应用消息
        """
        event_id = ""
        if hasattr(platform_message, "header") and hasattr(platform_message.header, "event_id"):
            event_id = platform_message.header.event_id

        app_id = platform_message.header.app_id
        event_key = platform_message.event.event_key
        user_open_id = platform_message.event.operator.operator_id.open_id
        content = ""
        msg_type = MessageType.MENU_CLICK

        return Message(
            msg_type=msg_type,
            content=content,
            sender_id=user_open_id,
            message_id=event_id,
            extra_data={"app_id": app_id, "event_key": event_key}
        )

    def parse_message(self, platform_message: Any) -> Message:
        """
        将飞书消息转换为统一消息结构

        Args:
            platform_message: 飞书消息事件数据

        Returns:
            Message: 统一消息结构
        """
        event_id = ""
        if hasattr(platform_message, "header") and hasattr(platform_message.header, "event_id"):
            event_id = platform_message.header.event_id

        msg_data = platform_message.event.message
        sender_id = platform_message.event.sender.sender_id.open_id
        chat_id = msg_data.chat_id
        message_id = msg_data.message_id
        chat_type = getattr(platform_message.event.message, "chat_type", "")

        # 根据消息类型解析内容
        content = ""
        msg_type = MessageType.UNKNOWN
        extra_data = {"event_id": event_id, "chat_type": chat_type}

        if msg_data.message_type == "text":
            content = json.loads(msg_data.content)["text"]
            msg_type = MessageType.TEXT
        elif msg_data.message_type == "image":
            content = msg_data.content
            msg_type = MessageType.IMAGE
            # 记录image_key方便后续处理

            image_content = json.loads(content)
            image_key = image_content.get("image_key")
            if image_key:
                extra_data["image_key"] = image_key
        elif msg_data.message_type == "audio":
            content = msg_data.content
            msg_type = MessageType.AUDIO
            # 记录file_key方便后续处理
            audio_content = json.loads(content)
            file_key = audio_content.get("file_key")
            if file_key:
                extra_data["file_key"] = file_key
        elif msg_data.message_type == "file":
            content = msg_data.content
            msg_type = MessageType.FILE
        elif msg_data.message_type == "post":
            content = msg_data.content
            msg_type = MessageType.POST
        else:
            content = f"Unsupported message type: {msg_data.message_type}"

        return Message(
            msg_type=msg_type,
            content=content,
            sender_id=sender_id,
            message_id=message_id,
            chat_id=chat_id,
            extra_data=extra_data
        )

    async def send_message(self, response: MessageResponse) -> bool:
        """
        发送消息

        Args:
            response: 响应消息

        Returns:
            bool: 是否成功
        """
        receive_id = response.extra_data.get('receive_id', '')
        if not receive_id:
            print("[FeishuMessageHandler] 发送消息失败：缺少接收者ID")
            return False

        if 'action' in response.extra_data:
            # 处理特殊操作
            action = response.extra_data.get('action', '')
            return await self._handle_action(action, response, receive_id)

        # 普通消息处理
        content = response.content
        if response.msg_type == MessageType.TEXT:
            req = CreateMessageRequest()
            req.payload = CreateMessageRequestBody(
                receive_id=receive_id,
                msg_type="text",
                content=content
            )
        else:
            # 其他类型消息处理
            print(f"[FeishuMessageHandler] 不支持的消息类型: {response.msg_type}")
            return False

        try:
            # 发送消息
            response = self.client.im.v1.message.create(req)
            return response.code == 0
        except Exception as e:
            print(f"[FeishuMessageHandler] 发送消息失败: {e}")
            return False

    def reply_message(self, original_message: Message, response: MessageResponse) -> bool:
        """
        回复消息

        Args:
            original_message: 原始消息
            response: 消息响应对象

        Returns:
            bool: 是否回复成功
        """
        # 根据action执行特殊操作
        action = response.extra_data.get("action", "")
        if action:
            # 如果是处理特殊操作，需要通过异步方式处理
            # 创建异步任务处理函数
            async def process_action():
                return await self._handle_action(action, response, original_message.chat_id, original_message)

            # 创建一个Future对象来获取异步操作的结果
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(process_action(), loop)

            try:
                # 等待操作完成并获取结果 (设置10秒超时)
                return future.result(10)
            except Exception as e:
                print(f"[FeishuMessageHandler] 异步处理操作失败: {e}")
                return False

        # 如果是p2p对话，使用chat_id发送
        if original_message.extra_data.get("chat_type", "") == "p2p":
            request = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                CreateMessageRequestBody.builder()
                .receive_id(original_message.chat_id)
                .msg_type(response.msg_type.value)
                .content(response.content)
                .build()
            ).build()
            feishu_response = self.client.im.v1.message.create(request)
            return feishu_response.success()

        # 普通回复
        request = (
            ReplyMessageRequest.builder()
            .message_id(original_message.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(response.content)
                .msg_type(response.msg_type.value)
                .build()
            )
            .build()
        )
        feishu_response = self.client.im.v1.message.reply(request)
        return feishu_response.success()

    def get_resource(self, message: Message, resource_key: str) -> Optional[bytes]:
        """
        获取消息中的资源（图片、音频等）

        Args:
            message: 消息对象
            resource_key: 资源标识键

        Returns:
            Optional[bytes]: 资源二进制数据，若获取失败则返回None
        """
        resource_type = "file"
        if message.msg_type == MessageType.IMAGE:
            resource_type = "image"

        request = GetMessageResourceRequest.builder() \
            .message_id(message.message_id) \
            .file_key(resource_key) \
            .type(resource_type) \
            .build()

        response = self.client.im.v1.message_resource.get(request)

        if not response.success():
            debug_utils.log_and_print(f"获取资源文件失败: {response.code} - {response.msg}", log_level="ERROR")
            return None

        return response.file.read()

    def upload_resource(
            self, resource_type: MessageType, resource_data: bytes,
            file_name: str = "", **kwargs) -> Optional[str]:
        """
        上传资源（图片、音频等）

        Args:
            resource_type: 资源类型
            resource_data: 资源二进制数据
            file_name: 文件名
            **kwargs: 其他参数

        Returns:
            Optional[str]: 资源标识键，若上传失败则返回None
        """
        if resource_type == MessageType.IMAGE:
            # 上传图片
            image_file = BytesIO(resource_data)
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

            if (
                upload_response.success() and
                upload_response.data and
                upload_response.data.image_key
            ):
                return upload_response.data.image_key

        elif resource_type == MessageType.AUDIO:
            # 上传音频文件
            audio_file = BytesIO(resource_data)
            duration = kwargs.get("duration", "0")

            upload_response = self.client.im.v1.file.create(
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type("opus")
                    .file_name(file_name or "audio.opus")
                    .duration(str(duration))
                    .file(audio_file)
                    .build()
                ).build()
            )

            if upload_response.success() and upload_response.data and upload_response.data.file_key:
                return upload_response.data.file_key

        # 其他文件类型暂不支持
        return None

    async def _handle_action(
            self, action: str, response: MessageResponse,
            receive_id: str, original_message: Message = None) -> bool:
        """
        处理特殊操作

        Args:
            action: 操作类型
            response: 响应消息
            receive_id: 接收者ID
            original_message: 原始消息

        Returns:
            bool: 是否成功
        """
        # 根据action类型创建对应的处理器
        handler = self._create_handler(action, self.client, self.bot_service)
        if handler:
            # 准备参数
            receive_id_type = 'open_id'
            kwargs = {
                'original_message': original_message,
                'response': response,
                'value': response.extra_data.get('value', {}),
            }

            # 对于特定操作，提取额外参数
            if action == 'generate_image':
                kwargs['prompt'] = response.extra_data.get('prompt', '')
            elif action == 'generate_tts':
                kwargs['text'] = response.extra_data.get('text', '')
            elif action == 'process_image':
                kwargs['image_key'] = response.extra_data.get('image_key', '')

            # 处理操作
            return await handler.handle(receive_id, receive_id_type, **kwargs)
        else:
            # 默认处理
            if self.bot_service:
                print(f"[FeishuMessageHandler] 未知操作类型: {action}")
                return False
            return False

    def _create_handler(self, action: str, client, bot_service):
        """
        创建处理器

        Args:
            action: 动作名称
            client: 客户端
            bot_service: 机器人服务

        Returns:
            FeishuActionHandler: 处理器对象
        """
        return ActionHandlerFactory.create_handler(action, client, bot_service)
