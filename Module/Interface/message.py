"""
消息接口定义

定义平台无关的消息结构和处理接口
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional


class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    FILE = "file"
    POST = "post"  # 富文本
    MENU_CLICK = "menu_click"  # 菜单点击
    UNKNOWN = "unknown"


class Message:
    """平台无关的统一消息结构"""

    def __init__(
        self,
        msg_type: MessageType,
        content: str,
        sender_id: str,
        message_id: str = "",
        chat_id: str = "",
        extra_data: Dict[str, Any] = None
    ):
        self.msg_type = msg_type
        self.content = content
        self.sender_id = sender_id
        self.message_id = message_id
        self.chat_id = chat_id
        self.extra_data = extra_data or {}

    @property
    def is_text(self) -> bool:
        """是否为文本消息"""
        return self.msg_type == MessageType.TEXT

    @property
    def is_image(self) -> bool:
        """是否为图片消息"""
        return self.msg_type == MessageType.IMAGE

    @property
    def is_audio(self) -> bool:
        """是否为音频消息"""
        return self.msg_type == MessageType.AUDIO

    @property
    def is_file(self) -> bool:
        """是否为文件消息"""
        return self.msg_type == MessageType.FILE

    @property
    def is_post(self) -> bool:
        """是否为富文本消息"""
        return self.msg_type == MessageType.POST


class MessageResponse:
    """平台无关的统一消息响应结构"""

    def __init__(
        self,
        msg_type: MessageType,
        content: str,
        success: bool = True,
        error_msg: str = "",
        extra_data: Dict[str, Any] = None
    ):
        self.msg_type = msg_type
        self.content = content
        self.success = success
        self.error_msg = error_msg
        self.extra_data = extra_data or {}


class MessageHandler(ABC):
    """消息处理器抽象接口"""

    @abstractmethod
    def parse_message(self, platform_message: Any) -> Message:
        """
        将平台特定的消息转换为统一消息结构

        Args:
            platform_message: 平台特定的消息对象

        Returns:
            Message: 统一消息结构
        """

    @abstractmethod
    def send_message(self, response: MessageResponse) -> bool:
        """
        发送消息

        Args:
            response: 消息响应对象

        Returns:
            bool: 是否发送成功
        """

    @abstractmethod
    def reply_message(self, original_message: Message, response: MessageResponse) -> bool:
        """
        回复消息

        Args:
            original_message: 原始消息
            response: 消息响应对象

        Returns:
            bool: 是否回复成功
        """

    @abstractmethod
    def get_resource(self, message: Message, resource_key: str) -> Optional[bytes]:
        """
        获取消息中的资源（图片、音频等）

        Args:
            message: 消息对象
            resource_key: 资源标识键

        Returns:
            Optional[bytes]: 资源二进制数据，若获取失败则返回None
        """

    @abstractmethod
    def upload_resource(self, resource_type: MessageType, resource_data: bytes,
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
