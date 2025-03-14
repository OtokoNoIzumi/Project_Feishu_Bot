"""
飞书消息处理模块

该模块实现了飞书平台的消息处理
"""

from io import BytesIO
import json
import os
from typing import Any, Optional

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

    def send_message(self, response: MessageResponse) -> bool:
        """
        发送消息

        Args:
            response: 消息响应对象

        Returns:
            bool: 是否发送成功
        """
        # 从extra_data中获取接收者ID
        receive_id = response.extra_data.get("receive_id", os.getenv("ADMIN_ID", ""))

        # 根据action执行特殊操作
        action = response.extra_data.get("action", "")
        if action:
            return self._handle_action(action, response, receive_id)

        # 普通消息发送
        request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(response.msg_type.value)
            .content(response.content)
            .build()
        ).build()

        feishu_response = self.client.im.v1.message.create(request)
        return feishu_response.success()

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
            # 获取原始消息数据
            message_data = original_message
            # 处理特殊操作
            handler = ActionHandlerFactory.create_handler(action, self.client, self.bot_service)
            if handler:
                receive_id = message_data.sender_id
                receive_id_type = "open_id"

                # 传递所有必要参数
                handler_result = handler.handle(
                    receive_id,
                    receive_id_type,
                    data=message_data,
                    message_id=message_data.message_id,
                    **response.extra_data
                )
                return handler_result is not False
            # 如果没有对应的处理器，尝试通过常规方法回复
            debug_utils.log_and_print(f"未找到操作处理器: {action}", log_level="WARNING")

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

    def _handle_action(
            self, action: str, response: MessageResponse,
            receive_id: str, original_message: Message = None) -> bool:
        """
        处理特殊操作

        Args:
            action: 操作类型
            response: 消息响应对象
            receive_id: 接收者ID
            original_message: 原始消息对象

        Returns:
            bool: 是否处理成功
        """
        # 默认使用open_id类型
        # 如果从reply_message调用，传入的是chat_id，应该使用chat_id类型
        receive_id_type = "chat_id" if original_message else "open_id"
        # receive_id_type = "open_id"

        # 如果是回复消息且原始消息是群聊，则使用chat_id
        # if original_message and original_message.extra_data.get("chat_type", "") != "p2p":
        #     receive_id_type = "chat_id"

        # 使用工厂创建对应的处理器
        handler = ActionHandlerFactory.create_handler(action, self.client, self.bot_service)

        # 准备处理参数
        kwargs = {}

        # 从response中提取参数
        for key, value in response.extra_data.items():
            if key != "action":
                kwargs[key] = value

        # 如果存在原始消息，添加message_id
        if original_message:
            kwargs["message_id"] = original_message.message_id
            kwargs["data"] = original_message  # 向后兼容之前的全量数据

        # 检查kwargs中是否已经包含receive_id，避免重复传参
        if "receive_id" in kwargs:
            # 如果kwargs中已有receive_id，则使用kwargs中的值
            return handler.handle(receive_id_type=receive_id_type, **kwargs)
        else:
            # 否则正常传递receive_id参数
            return handler.handle(receive_id=receive_id, receive_id_type=receive_id_type, **kwargs)

    def handle_card_action(self, action_data) -> dict:
        """
        处理卡片按钮点击事件

        Args:
            action_data: 卡片事件数据

        Returns:
            dict: 卡片回调响应
        """
        if not action_data or not hasattr(action_data, "event") or not hasattr(action_data.event, "action"):
            return {"text": "无效的卡片点击事件"}

        try:
            # 解析事件数据
            event = action_data.event
            action = event.action
            action_value = action.value

            # 获取触发动作
            if not isinstance(action_value, dict) or "action" not in action_value:
                return {"text": "未找到有效的卡片动作"}

            action_type = action_value["action"]

            # 创建处理器
            handler = ActionHandlerFactory.create_handler(action_type, self.client, self.bot_service)
            if not handler:
                return {
                    "toast": {
                        "type": "error",
                        "content": f"未找到处理器: {action_type}"
                    }
                }

            # 执行处理
            receive_id = event.operator.open_id
            receive_id_type = "open_id"
            result = handler.handle(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                value=action_value,
                is_card_action=True
            )

            # 如果处理器返回了卡片回调格式的结果，直接返回
            if isinstance(result, dict):
                return result

            # 否则返回简单的成功提示
            return {
                "toast": {
                    "type": "success",
                    "content": "操作成功"
                }
            }

        except Exception as e:
            debug_utils.log_and_print(f"处理卡片点击事件失败: {e}", log_level="ERROR")
            import traceback
            traceback.print_exc()

            return {
                "toast": {
                    "type": "error",
                    "content": "处理操作失败，请稍后重试"
                }
            }
