"""
消息处理器 (Message Processor)

核心业务逻辑，负责处理各种类型的消息
完全独立于前端平台，可以被任何适配器调用
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class MessageContext:
    """消息上下文 - 标准化的消息数据结构"""
    user_id: str
    user_name: str
    message_type: str  # text, image, audio, menu_click, card_action
    content: Any
    timestamp: datetime
    event_id: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ProcessResult:
    """处理结果 - 标准化的响应数据结构"""
    success: bool
    response_type: str  # text, image, audio, post
    response_content: Any
    error_message: str = None
    should_reply: bool = True

    @classmethod
    def success_result(cls, response_type: str, content: Any):
        return cls(True, response_type, content)

    @classmethod
    def error_result(cls, error_msg: str):
        return cls(False, "text", {"text": error_msg}, error_msg, True)

    @classmethod
    def no_reply_result(cls):
        return cls(True, "text", None, should_reply=False)


class MessageProcessor:
    """
    核心消息处理器

    职责：
    1. 接收标准化的消息上下文
    2. 执行平台无关的业务逻辑
    3. 返回标准化的处理结果
    """

    def __init__(self, app_controller=None):
        """
        初始化消息处理器

        Args:
            app_controller: 应用控制器，用于访问各种服务
        """
        self.app_controller = app_controller
        self._load_config()

    def _load_config(self):
        """加载配置"""
        if self.app_controller:
            # 从配置服务获取配置
            success, admin_id = self.app_controller.call_service('config', 'get', 'admin_id', '')
            self.admin_id = admin_id if success else ''

            success, trigger = self.app_controller.call_service('config', 'get', 'update_config_trigger', 'whisk令牌')
            self.update_config_trigger = trigger if success else 'whisk令牌'
        else:
            # 默认配置
            self.admin_id = ''
            self.update_config_trigger = 'whisk令牌'

    def process_message(self, context: MessageContext) -> ProcessResult:
        """
        处理消息的主入口

        Args:
            context: 消息上下文

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 检查事件是否已处理（去重）
            if self._is_duplicate_event(context.event_id):
                return ProcessResult.no_reply_result()

            # 记录新事件
            self._record_event(context)

            # 根据消息类型分发处理
            if context.message_type == "text":
                return self._process_text_message(context)
            elif context.message_type == "image":
                return self._process_image_message(context)
            elif context.message_type == "audio":
                return self._process_audio_message(context)
            elif context.message_type == "menu_click":
                return self._process_menu_click(context)
            elif context.message_type == "card_action":
                return self._process_card_action(context)
            else:
                return ProcessResult.error_result(f"不支持的消息类型: {context.message_type}")

        except Exception as e:
            return ProcessResult.error_result(f"消息处理失败: {str(e)}")

    def _is_duplicate_event(self, event_id: str) -> bool:
        """检查事件是否重复"""
        if self.app_controller:
            success, result = self.app_controller.call_service('cache', 'get', f"event:{event_id}")
            return success and result is not None
        return False

    def _record_event(self, context: MessageContext):
        """记录新事件"""
        if self.app_controller:
            # 记录事件ID
            self.app_controller.call_service('cache', 'set', f"event:{context.event_id}",
                                           context.timestamp.isoformat(), 86400)  # 24小时过期

            # 更新用户缓存
            self.app_controller.call_service('cache', 'set', f"user:{context.user_id}",
                                           context.user_name, 604800)  # 7天过期

    def _process_text_message(self, context: MessageContext) -> ProcessResult:
        """处理文本消息"""
        user_msg = context.content

        # 管理员配置更新指令
        if user_msg.startswith(self.update_config_trigger):
            return self._handle_config_update(context, user_msg)

        # 基础指令处理
        if "帮助" in user_msg:
            return self._handle_help_command(context)
        elif "你好" in user_msg:
            return self._handle_greeting_command(context)
        else:
            # 默认回复
            return ProcessResult.success_result("text", {
                "text": f"收到你发送的消息：{user_msg}"
            })

    def _process_image_message(self, context: MessageContext) -> ProcessResult:
        """处理图片消息"""
        return ProcessResult.success_result("text", {
            "text": "收到图片消息，图片处理功能将在后续版本实现"
        })

    def _process_audio_message(self, context: MessageContext) -> ProcessResult:
        """处理音频消息"""
        return ProcessResult.success_result("text", {
            "text": "收到音频消息，音频处理功能将在后续版本实现"
        })

    def _process_menu_click(self, context: MessageContext) -> ProcessResult:
        """处理菜单点击"""
        event_key = context.content

        # 根据菜单键处理不同功能
        if event_key == "send_alarm":
            return ProcessResult.success_result("text", {
                "text": "🚨 收到告警菜单点击，告警功能将在后续版本实现"
            })
        elif event_key == "get_bili_url":
            return ProcessResult.success_result("text", {
                "text": "📺 收到B站推荐菜单点击，推荐功能将在后续版本实现"
            })
        else:
            return ProcessResult.success_result("text", {
                "text": f"收到菜单点击：{event_key}，功能开发中..."
            })

    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片按钮动作"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        # 根据动作类型处理
        if action == "send_alarm":
            return ProcessResult.success_result("text", {
                "text": "🚨 收到告警卡片点击，告警功能将在后续版本实现"
            })
        elif action == "confirm_action":
            return ProcessResult.success_result("text", {
                "text": "✅ 操作已确认"
            })
        else:
            return ProcessResult.success_result("text", {
                "text": f"收到卡片动作：{action}，功能开发中..."
            })

    def _handle_config_update(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理配置更新指令"""
        # 验证管理员权限
        if context.user_id != self.admin_id:
            return ProcessResult.success_result("text", {
                "text": f"收到消息：{user_msg}"
            })

        # 解析配置更新指令
        command_parts = user_msg[len(self.update_config_trigger):].strip().split(maxsplit=1)
        if len(command_parts) != 2:
            return ProcessResult.error_result(
                f"格式错误，请使用 '{self.update_config_trigger} 变量名 新值' 格式"
            )

        variable_name, new_value = command_parts
        # 这里后续会实现具体的配置更新逻辑
        return ProcessResult.success_result("text", {
            "text": f"配置更新功能将在后续版本实现：{variable_name} = {new_value}"
        })

    def _handle_help_command(self, context: MessageContext) -> ProcessResult:
        """处理帮助指令"""
        help_text = """<b>阶段1 MVP - 基础功能</b>

当前支持的功能：
1. <b>基础对话</b> - 发送任意文本消息
2. <b>问候功能</b> - 输入"你好"获得问候回复
3. <b>帮助菜单</b> - 输入"帮助"查看此菜单
4. <b>菜单交互</b> - 支持机器人菜单点击
5. <b>卡片交互</b> - 支持卡片按钮点击

<i>架构优势：统一的交互处理，易于扩展</i>"""

        return ProcessResult.success_result("text", {"text": help_text})

    def _handle_greeting_command(self, context: MessageContext) -> ProcessResult:
        """处理问候指令"""
        return ProcessResult.success_result("text", {
            "text": f"你好，{context.user_name}！有什么我可以帮你的吗？"
        })

    def get_status(self) -> Dict[str, Any]:
        """获取处理器状态"""
        return {
            "processor_type": "MessageProcessor",
            "admin_id": self.admin_id,
            "update_config_trigger": self.update_config_trigger,
            "app_controller_available": self.app_controller is not None,
            "supported_message_types": ["text", "image", "audio", "menu_click", "card_action"]
        }