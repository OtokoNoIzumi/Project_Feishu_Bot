"""
飞书适配器 (Feishu Adapter)

职责：
1. 处理飞书WebSocket连接
2. 飞书消息格式与标准格式的转换
3. 调用核心业务处理器
4. 将处理结果转换为飞书消息格式发送
"""

import os
import json
import time
import datetime
from typing import Optional, Dict, Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)
from lark_oapi.api.contact.v3 import GetUserRequest
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

from Module.Business.message_processor import MessageContext, ProcessResult
from Module.Common.scripts.common import debug_utils


class FeishuAdapter:
    """
    飞书平台适配器

    职责：纯粹的协议转换和平台接口封装
    不包含任何业务逻辑，只负责与飞书平台的交互

    支持的交互类型：
    - 消息交互 (文本、图片、音频)
    - 菜单交互 (机器人菜单点击)
    - 卡片交互 (卡片按钮点击)
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

    def _handle_feishu_message(self, data) -> None:
        """
        处理飞书消息事件

        这是飞书SDK的回调函数，负责：
        1. 将飞书消息转换为标准格式
        2. 调用业务处理器
        3. 将处理结果转换为飞书消息发送
        """
        try:
            # 转换为标准消息上下文
            context = self._convert_message_to_context(data)
            if not context:
                return

            debug_utils.log_and_print(
                f"收到消息 - 用户: {context.user_name}({context.user_id})",
                f"类型: {context.message_type}, 内容: {context.content}",
                log_level="INFO"
            )

            # 调用业务处理器
            result = self.message_processor.process_message(context)

            # 发送回复
            if result.should_reply:
                self._send_feishu_reply(data, result)

        except Exception as e:
            debug_utils.log_and_print(f"飞书消息处理失败: {e}", log_level="ERROR")
            # 发送错误回复
            try:
                error_result = ProcessResult.error_result("消息处理出现错误")
                self._send_feishu_reply(data, error_result)
            except:
                pass  # 避免二次错误

    def _handle_feishu_menu(self, data) -> None:
        """
        处理飞书菜单点击事件

        将菜单点击转换为标准消息上下文处理
        """
        try:
            # 转换为标准消息上下文
            context = self._convert_menu_to_context(data)
            if not context:
                return

            debug_utils.log_and_print(
                f"收到菜单点击 - 用户: {context.user_name}({context.user_id})",
                f"菜单键: {context.content}",
                log_level="INFO"
            )

            # 调用业务处理器
            result = self.message_processor.process_message(context)

            # 发送回复（菜单点击通常需要主动发送消息）
            if result.should_reply:
                self._send_direct_message(context.user_id, result)

        except Exception as e:
            debug_utils.log_and_print(f"飞书菜单处理失败: {e}", log_level="ERROR")

    def _handle_feishu_card(self, data) -> P2CardActionTriggerResponse:
        """
        处理飞书卡片按钮点击事件

        将卡片点击转换为标准消息上下文处理
        """
        try:
            # 转换为标准消息上下文
            context = self._convert_card_to_context(data)
            if not context:
                return P2CardActionTriggerResponse({})

            debug_utils.log_and_print(
                f"收到卡片点击 - 用户: {context.user_name}({context.user_id})",
                f"动作: {context.content}",
                log_level="INFO"
            )

            # 调用业务处理器
            result = self.message_processor.process_message(context)

            # 卡片回调可以返回提示信息
            if result.success:
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

        except Exception as e:
            debug_utils.log_and_print(f"飞书卡片处理失败: {e}", log_level="ERROR")
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": "处理操作失败，请稍后重试"
                }
            })

    def _convert_message_to_context(self, data) -> Optional[MessageContext]:
        """将飞书消息转换为标准消息上下文"""
        try:
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

            return MessageContext(
                user_id=user_id,
                user_name=user_name,
                message_type=message_type,
                content=content,
                timestamp=timestamp,
                event_id=event_id,
                metadata={
                    'chat_id': data.event.message.chat_id,
                    'message_id': data.event.message.message_id,
                    'chat_type': data.event.message.chat_type,
                    'interaction_type': 'message'
                }
            )

        except Exception as e:
            debug_utils.log_and_print(f"消息转换失败: {e}", log_level="ERROR")
            return None

    def _convert_menu_to_context(self, data) -> Optional[MessageContext]:
        """将飞书菜单点击转换为标准消息上下文"""
        try:
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

        except Exception as e:
            debug_utils.log_and_print(f"菜单转换失败: {e}", log_level="ERROR")
            return None

    def _convert_card_to_context(self, data) -> Optional[MessageContext]:
        """将飞书卡片点击转换为标准消息上下文"""
        try:
            # 提取基本信息
            event_id = f"card_{data.event.operator.open_id}_{int(time.time())}"  # 卡片事件生成ID
            timestamp = datetime.datetime.now()

            # 提取用户信息
            user_id = data.event.operator.open_id
            user_name = self._get_user_name(user_id)

            # 卡片动作信息
            action = data.event.action
            action_value = action.value if hasattr(action, 'value') else {}

            return MessageContext(
                user_id=user_id,
                user_name=user_name,
                message_type="card_action",  # 自定义类型
                content=action_value.get('action', 'unknown_action'),
                timestamp=timestamp,
                event_id=event_id,
                metadata={
                    'action_value': action_value,
                    'interaction_type': 'card'
                }
            )

        except Exception as e:
            debug_utils.log_and_print(f"卡片转换失败: {e}", log_level="ERROR")
            return None

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

    def _get_user_name(self, open_id: str) -> str:
        """获取用户名称"""
        # 先从缓存获取
        if self.app_controller:
            success, cached_name = self.app_controller.call_service('cache', 'get', f"user:{open_id}")
            if success and cached_name:
                return cached_name

        # 从飞书API获取
        try:
            request = GetUserRequest.builder().user_id_type("open_id").user_id(open_id).build()
            response = self.client.contact.v3.user.get(request)
            if response.success() and response.data and response.data.user:
                name = response.data.user.name
                # 缓存用户名
                if self.app_controller:
                    self.app_controller.call_service('cache', 'set', f"user:{open_id}", name, 604800)
                return name
        except Exception as e:
            debug_utils.log_and_print(f"获取用户名失败: {e}", log_level="WARNING")

        return f"用户_{open_id[:8]}"

    def _send_feishu_reply(self, original_data, result: ProcessResult) -> bool:
        """发送飞书回复（用于消息回复）"""
        try:
            if not result.response_content:
                return True

            # 转换响应内容为飞书格式
            content_json = json.dumps(result.response_content)

            # 根据聊天类型选择发送方式
            if original_data.event.message.chat_type == "p2p":
                # 私聊
                request = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(original_data.event.message.chat_id)
                    .msg_type(result.response_type)
                    .content(content_json)
                    .build()
                ).build()
                response = self.client.im.v1.message.create(request)
            else:
                # 群聊
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

        except Exception as e:
            debug_utils.log_and_print(f"发送飞书回复失败: {e}", log_level="ERROR")
            return False

    def _send_direct_message(self, user_id: str, result: ProcessResult) -> bool:
        """发送直接消息（用于菜单点击等主动发送）"""
        try:
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

        except Exception as e:
            debug_utils.log_and_print(f"发送飞书直接消息失败: {e}", log_level="ERROR")
            return False

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