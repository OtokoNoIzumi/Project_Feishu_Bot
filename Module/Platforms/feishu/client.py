"""
飞书平台客户端实现模块

该模块实现了飞书平台的客户端，包括初始化、事件处理等功能
"""

import os
from typing import Any, Dict, Callable, Optional
import asyncio
import traceback
import json

import lark_oapi as lark
from lark_oapi.api.contact.v3 import GetUserRequest
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from Module.Interface.platform import Platform
from Module.Interface.message import Message, MessageResponse, MessageType, MessageHandler
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
                .register_p2_application_bot_menu_v6(self._handle_application_bot_menu_v6)  # 注册菜单处理器
                .register_p2_card_action_trigger(self._handle_im_message_action_v1)  # 注册卡片交互处理器
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
        """停止平台服务，很可能有问题"""
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
        # event_time = data.header.create_time or time.time()
        event_id = data.header.event_id
        sender_name = self.get_user_name(message.sender_id)

        # 记录详细日志
        print('--------------------------------')
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
            # print(f"[DEBUG] 收到消息，开始处理: {message}")
            # print(f"[DEBUG] 收到消息，开始处理: {message.__dict__}")
            response = self.bot_service.handle_message(message)
            if response:
                # 回复消息
                self.message_handler.reply_message(message, response)

    def _handle_application_bot_menu_v6(self, data) -> None:
        """
        处理机器人菜单点击事件

        Args:
            data: 事件数据
        """
        if not self.event_handler and not self.bot_service:
            return

        try:
            # 解析事件数据
            event_data = data.event
            open_id = event_data.operator.operator_id.open_id
            event_key = event_data.event_key

            # 创建Message对象
            message = self.message_handler.parse_bot_menu_click(data)

            # 如果事件已被处理，跳过
            if message.extra_data.get("event_id") and \
                self.bot_service.cache_service.check_event(message.extra_data.get("event_id")):
                debug_utils.log_and_print(f"重复的菜单点击事件，跳过处理", log_level="INFO")
                return

            if self.bot_service:
                # 处理消息
                response = self.bot_service.handle_message(message)

                # 如果有响应，创建任务处理
                if response:
                    # 记录事件处理
                    event_id = message.extra_data.get("event_id")
                    if event_id:
                        self.bot_service.cache_service.add_event(event_id)

                    # 创建异步任务处理器函数
                    async def process_async_action():
                        try:
                            await self.message_handler.send_message(response)
                        except Exception as e:
                            debug_utils.log_and_print(f"异步处理消息失败: {e}", log_level="ERROR")

                    # 在新线程中运行异步任务
                    asyncio.run_coroutine_threadsafe(
                        process_async_action(),
                        asyncio.get_event_loop()
                    )

            elif self.event_handler:
                response = self.event_handler(message)
                if response:
                    # 在新线程中运行异步发送
                    async def send_async():
                        await self.message_handler.send_message(response)

                    asyncio.run_coroutine_threadsafe(
                        send_async(),
                        asyncio.get_event_loop()
                    )

        except Exception as e:
            debug_utils.log_and_print(f"处理菜单点击事件失败: {e}", log_level="ERROR")
            debug_utils.log_and_print(traceback.format_exc(), log_level="DEBUG")

    def _handle_im_message_action_v1(self, data) -> None:
        """
        处理飞书卡片交互事件

        Args:
            data: 卡片交互事件数据
        """
        try:
            # 提取事件信息
            event_id = data.header.event_id
            action = data.event.action

            # 如果事件已被处理，跳过
            if self.bot_service and self.bot_service.cache_service.check_event(event_id):
                debug_utils.log_and_print(f"重复的卡片交互事件，跳过处理", log_level="INFO")
                return

            print(f"[DEBUG] 收到卡片交互事件: {event_id}, action类型: {type(action)}")
            print(f"[DEBUG] 卡片交互action内容: {action}")

            # 记录事件
            if self.bot_service:
                self.bot_service.cache_service.add_event(event_id)

            # 提取必要的信息
            value = action.value
            open_id = data.event.operator.operator_id.open_id

            # 提取action类型
            action_type = ""
            if isinstance(value, dict):
                action_type = value.get("action", "")
            elif isinstance(value, str):
                try:
                    value_dict = json.loads(value)
                    action_type = value_dict.get("action", "")
                except:
                    pass

            print(f"[DEBUG] 卡片交互动作类型: {action_type}, 用户ID: {open_id}")

            # 调用对应的处理器
            if action_type and self.bot_service:
                # 创建异步任务处理函数
                async def process_action():
                    try:
                        handler = self.message_handler._create_handler(action_type, self.client, self.bot_service)
                        if handler:
                            await handler.handle(open_id, "open_id", value=value)
                        else:
                            print(f"[ERROR] 未找到处理器: {action_type}")
                    except Exception as e:
                        print(f"[ERROR] 处理卡片交互失败: {e}")
                        print(traceback.format_exc())

                # 在事件循环中运行
                if asyncio.get_event_loop().is_running():
                    asyncio.run_coroutine_threadsafe(process_action(), asyncio.get_event_loop())
                else:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(process_action())

        except Exception as e:
            debug_utils.log_and_print(f"处理卡片交互事件失败: {e}", log_level="ERROR")
            debug_utils.log_and_print(traceback.format_exc(), log_level="DEBUG")
