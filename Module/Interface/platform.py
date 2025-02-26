"""
平台接口定义

定义不同平台实现必须遵循的接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
from Module.Interface.message import Message, MessageResponse, MessageHandler


class Platform(ABC):
    """平台抽象接口"""

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化平台

        Args:
            config: 配置信息

        Returns:
            bool: 是否初始化成功
        """
        pass

    @abstractmethod
    def get_message_handler(self) -> MessageHandler:
        """
        获取消息处理器

        Returns:
            MessageHandler: 消息处理器
        """
        pass

    @abstractmethod
    def register_event_handler(self, handler: Callable[[Message], Optional[MessageResponse]]) -> None:
        """
        注册事件处理器

        Args:
            handler: 事件处理函数，接收Message对象，返回MessageResponse或None
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """启动平台服务"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止平台服务"""
        pass