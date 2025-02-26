"""
飞书平台客户端实现模块

该模块实现了飞书平台的客户端，包括初始化、事件处理等功能
"""

import os
import time
from typing import Any, Dict, Callable, Optional, List

import lark_oapi as lark
from lark_oapi.api.contact.v3 import GetUserRequest

from Module.Interface.platform import Platform
from Module.Interface.message import Message, MessageResponse, MessageHandler
from Module.Platforms.feishu.message_handler import FeishuMessageHandler
from Module.Core.bot_service import BotService
from Module.Common.scripts.common import debug_utils


class FeishuPlatform(Platform):
    """飞书平台实现"""

    def __init__(self):
        """初始化飞书平台"""
        self.app_id = None
        self.app_secret = None
        self.client = None
        self.ws_client = None
        self.message_handler = None
        self.event_handler = None
        self.bot_service = None
        self.log_level = "DEBUG"

    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化平台

        Args:
            config: 配置信息

        Returns:
            bool: 是否初始化成功
        """
        try:
            # 设置飞书应用凭证
            self.app_id = config.get("app_id") or os.getenv("FEISHU_APP_MESSAGE_ID", "")
            self.app_secret = config.get("app_secret") or os.getenv("FEISHU_APP_MESSAGE_SECRET", "")
            self.log_level = config.get("log_level", "DEBUG")

            # 设置lark全局配置
            lark.APP_ID = self.app_id
            lark.APP_SECRET = self.app_secret

            # 创建客户端
            self.client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()

            # 创建消息处理器
            # 注意：此时bot_service还未注册，将在register_bot_service中重新设置message_handler
            self.message_handler = FeishuMessageHandler(self.client)

            # 设置WebSocket客户端
            ws_log_level = lark.LogLevel[self.log_level]
            event_dispatcher = (
                lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(self._handle_p2_im_message_receive_v1)
                .build()
            )
            self.ws_client = lark.ws.Client(
                self.app_id,
                self.app_secret,
                event_handler=event_dispatcher,
                log_level=ws_log_level
            )

            return True
        except Exception as e:
            debug_utils.log_and_print(f"飞书平台初始化失败: {e}", log_level="ERROR")
            return False

    def get_message_handler(self) -> MessageHandler:
        """
        获取消息处理器

        Returns:
            MessageHandler: 消息处理器
        """
        return self.message_handler

    def register_event_handler(self, handler: Callable[[Message], Optional[MessageResponse]]) -> None:
        """
        注册事件处理器

        Args:
            handler: 事件处理函数，接收Message对象，返回MessageResponse或None
        """
        self.event_handler = handler

    def register_bot_service(self, bot_service: BotService) -> None:
        """
        注册机器人服务

        Args:
            bot_service: 机器人服务实例
        """
        self.bot_service = bot_service
        # 更新消息处理器，传入bot_service
        self.message_handler = FeishuMessageHandler(self.client, self.bot_service)

    def start(self) -> None:
        """启动平台服务"""
        if not self.ws_client:
            debug_utils.log_and_print("WebSocket客户端未初始化，无法启动", log_level="ERROR")
            return

        self.ws_client.start()
        debug_utils.log_and_print("飞书平台WebSocket连接已建立，等待接收消息...", log_level="INFO")

    def stop(self) -> None:
        """停止平台服务"""
        if self.ws_client:
            self.ws_client.stop()
            debug_utils.log_and_print("飞书平台WebSocket连接已关闭", log_level="INFO")

    async def start_async(self) -> None:
        """异步启动平台服务"""
        if not self.ws_client:
            debug_utils.log_and_print("WebSocket客户端未初始化，无法启动", log_level="ERROR")
            return

        # 使用底层连接方法进行异步连接
        await self.ws_client._connect()
        debug_utils.log_and_print("飞书平台WebSocket连接已建立，等待接收消息...", log_level="INFO")

    def get_user_name(self, open_id: str) -> str:
        """
        获取用户名称

        Args:
            open_id: 用户Open ID

        Returns:
            str: 用户名称
        """
        # 首先尝试从缓存服务获取
        if self.bot_service and self.bot_service.cache_service:
            cached_name = self.bot_service.cache_service.get_user_name(open_id)
            if cached_name:
                return f"{cached_name}(缓存)"

        # 调用API获取
        request = GetUserRequest.builder() \
            .user_id(open_id) \
            .user_id_type("open_id") \
            .department_id_type("department_id") \
            .build()

        try:
            response = self.client.contact.v3.user.get(request)
            if response.success() and response.data and response.data.user:
                name = response.data.user.name
                # 更新缓存
                if self.bot_service and self.bot_service.cache_service:
                    self.bot_service.cache_service.update_user(open_id, name)
                    self.bot_service.cache_service.save_user_cache()
                return name
        except Exception as e:
            debug_utils.log_and_print(f"获取用户信息失败: {e}", log_level="ERROR")

        return "未知用户"

    def send_message(self, receive_id: str, msg_type: str, content: str) -> bool:
        """
        发送消息

        Args:
            receive_id: 接收者ID
            msg_type: 消息类型
            content: 消息内容

        Returns:
            bool: 是否发送成功
        """
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        request = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        ).build()

        response = self.client.im.v1.message.create(request)

        return response.success()

    def _handle_p2_im_message_receive_v1(self, data) -> None:
        """
        处理飞书消息接收事件

        Args:
            data: 飞书事件数据
        """
        # 解析消息
        message = self.message_handler.parse_message(data)

        # 记录基本信息
        event_time = data.header.create_time or time.time()
        event_id = data.header.event_id
        sender_name = self.get_user_name(message.sender_id)

        # 记录详细日志
        print('\n\ntest_data', message.__dict__)
        debug_utils.log_and_print(
            f"收到消息事件 - ID: {event_id}",
            f"发送者: {sender_name} ({message.sender_id})",
            f"消息类型: {message.msg_type}",
            log_level="INFO"
        )
        # 调用处理器处理消息
        if self.event_handler:
            response = self.event_handler(message)
            if response:
                # 回复消息
                self.message_handler.reply_message(message, response)
        elif self.bot_service:
            # 直接使用BotService处理
            print(f"[DEBUG] 收到消息，开始处理: {message}")
            print(f"[DEBUG] 收到消息，开始处理: {message.__dict__}")
            response = self.bot_service.handle_message(message)
            if response:
                # 回复消息
                self.message_handler.reply_message(message, response)