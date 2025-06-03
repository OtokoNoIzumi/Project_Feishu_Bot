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
        from Module.Common.scripts.common import debug_utils

        if not self.app_controller:
            debug_utils.log_and_print("app_controller为空，无法检查重复事件", log_level="WARNING")
            return False

        cache_service = self.app_controller.get_service('cache')
        if not cache_service:
            debug_utils.log_and_print("缓存服务不可用，无法检查重复事件", log_level="WARNING")
            return False

        # 直接调用缓存服务的check_event方法
        is_duplicate = cache_service.check_event(event_id)
        # debug_utils.log_and_print(f"🔍 事件检查 - ID: {event_id[:16]}..., 重复: {is_duplicate}", log_level="INFO")

        if is_duplicate:
            debug_utils.log_and_print(
                f"🔄 重复消息已跳过 - ID: {event_id[:16]}...",
                log_level="INFO"
            )

        return is_duplicate

    def _record_event(self, context: MessageContext):
        """记录新事件"""
        from Module.Common.scripts.common import debug_utils

        if not self.app_controller:
            debug_utils.log_and_print("app_controller为空，无法记录事件", log_level="WARNING")
            return

        cache_service = self.app_controller.get_service('cache')
        if not cache_service:
            debug_utils.log_and_print("缓存服务不可用，无法记录事件", log_level="WARNING")
            return

        # 直接调用缓存服务的方法
        cache_service.add_event(context.event_id)
        cache_service.save_event_cache()
        # debug_utils.log_and_print(f"✅ 事件已记录 - ID: {context.event_id}...", log_level="INFO")

        # 更新用户缓存
        cache_service.update_user(context.user_id, context.user_name)

    def _process_text_message(self, context: MessageContext) -> ProcessResult:
        """处理文本消息"""
        user_msg = context.content

        # 管理员配置更新指令
        if user_msg.startswith(self.update_config_trigger):
            return self._handle_config_update(context, user_msg)

        # TTS配音指令
        if "配音" in user_msg:
            return self._handle_tts_command(context, user_msg)

        # 图像生成指令
        if "生图" in user_msg or "AI画图" in user_msg:
            return self._handle_image_generation_command(context, user_msg)

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
        """处理图片消息 - 图像风格转换"""
        try:
            # 检查图像服务是否可用
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            image_service = self.app_controller.get_service('image')
            if not image_service or not image_service.is_available():
                return ProcessResult.error_result("图像处理服务未启动或不可用")

            # 先发送处理中提示
            return ProcessResult.success_result("text", {
                "text": "正在转换图片风格，请稍候...",
                "next_action": "process_image_conversion",
                "image_data": context.content  # 图像数据将由适配器传递
            })

        except Exception as e:
            return ProcessResult.error_result(f"图像消息处理失败: {str(e)}")

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

    def _handle_tts_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理TTS配音指令"""
        try:
            # 提取配音文本
            tts_text = user_msg.split("配音", 1)[1].strip()
            if not tts_text:
                return ProcessResult.error_result("配音文本不能为空，请使用格式：配音 文本内容")

            # 检查音频服务是否可用
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            audio_service = self.app_controller.get_service('audio')
            if not audio_service:
                return ProcessResult.error_result("音频服务未启动")

            # 先发送处理中提示
            return ProcessResult.success_result("text", {
                "text": "正在生成配音，请稍候...",
                "next_action": "process_tts",
                "tts_text": tts_text
            })

        except Exception as e:
            return ProcessResult.error_result(f"配音指令处理失败: {str(e)}")

    def process_tts_async(self, tts_text: str) -> ProcessResult:
        """
        异步处理TTS生成（由FeishuAdapter调用）

        Args:
            tts_text: 要转换的文本

        Returns:
            ProcessResult: 处理结果
        """
        try:
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            # 获取音频服务
            audio_service = self.app_controller.get_service('audio')
            if not audio_service:
                return ProcessResult.error_result("音频服务未启动")

            # 生成TTS音频
            success, audio_data, error_msg = audio_service.process_tts_request(tts_text)

            if not success:
                return ProcessResult.error_result(f"TTS生成失败: {error_msg}")

            # 返回音频数据，由适配器处理上传
            return ProcessResult.success_result("audio", {
                "audio_data": audio_data,
                "text": tts_text[:50] + ("..." if len(tts_text) > 50 else "")
            })

        except Exception as e:
            return ProcessResult.error_result(f"TTS异步处理失败: {str(e)}")

    def _handle_image_generation_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理图像生成指令"""
        try:
            # 提取生图文本
            if "生图" in user_msg:
                prompt = user_msg.split("生图", 1)[1].strip()
            elif "AI画图" in user_msg:
                prompt = user_msg.split("AI画图", 1)[1].strip()
            else:
                prompt = ""

            if not prompt:
                return ProcessResult.error_result("图像生成文本不能为空，请使用格式：生图 描述内容 或 AI画图 描述内容")

            # 检查图像服务是否可用
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            image_service = self.app_controller.get_service('image')
            if not image_service or not image_service.is_available():
                return ProcessResult.error_result("图像生成服务未启动或不可用")

            # 先发送处理中提示
            return ProcessResult.success_result("text", {
                "text": "正在生成图片，请稍候...",
                "next_action": "process_image_generation",
                "generation_prompt": prompt
            })

        except Exception as e:
            return ProcessResult.error_result(f"图像生成指令处理失败: {str(e)}")

    def process_image_generation_async(self, prompt: str) -> ProcessResult:
        """
        异步处理图像生成（由FeishuAdapter调用）

        Args:
            prompt: 图像生成提示词

        Returns:
            ProcessResult: 处理结果
        """
        try:
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            # 获取图像服务
            image_service = self.app_controller.get_service('image')
            if not image_service or not image_service.is_available():
                return ProcessResult.error_result("图像生成服务未启动或不可用")

            # 生成图像
            image_paths = image_service.process_text_to_image(prompt)

            if image_paths is None:
                return ProcessResult.error_result("图片生成故障，已经通知管理员修复咯！")
            elif len(image_paths) == 0:
                return ProcessResult.error_result("图片生成失败了，建议您换个提示词再试试")

            # 返回图像路径列表，由适配器处理上传
            return ProcessResult.success_result("image_list", {
                "image_paths": image_paths,
                "prompt": prompt[:50] + ("..." if len(prompt) > 50 else "")
            })

        except Exception as e:
            return ProcessResult.error_result(f"图像生成异步处理失败: {str(e)}")

    def process_image_conversion_async(self, image_base64: str, mime_type: str,
                                     file_name: str, file_size: int) -> ProcessResult:
        """
        异步处理图像风格转换（由FeishuAdapter调用）

        Args:
            image_base64: base64编码的图像数据
            mime_type: 图像MIME类型
            file_name: 文件名
            file_size: 文件大小

        Returns:
            ProcessResult: 处理结果
        """
        try:
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            # 获取图像服务
            image_service = self.app_controller.get_service('image')
            if not image_service or not image_service.is_available():
                return ProcessResult.error_result("图像转换服务未启动或不可用")

            # 处理图像转换
            image_paths = image_service.process_image_to_image(
                image_base64, mime_type, file_name, file_size
            )

            if image_paths is None:
                return ProcessResult.error_result("图片处理故障，已经通知管理员修复咯！")
            elif len(image_paths) == 0:
                return ProcessResult.error_result("图片处理失败了，请尝试使用其他图片")

            # 返回处理后的图像路径列表
            return ProcessResult.success_result("image_list", {
                "image_paths": image_paths,
                "original_file": file_name
            })

        except Exception as e:
            return ProcessResult.error_result(f"图像转换异步处理失败: {str(e)}")

    def _handle_help_command(self, context: MessageContext) -> ProcessResult:
        """处理帮助指令"""
        help_text = """<b>阶段2B MVP - 音频与图像处理功能</b>

当前支持的功能：
1. <b>基础对话</b> - 发送任意文本消息
2. <b>问候功能</b> - 输入"你好"获得问候回复
3. <b>帮助菜单</b> - 输入"帮助"查看此菜单
4. <b>菜单交互</b> - 支持机器人菜单点击
5. <b>卡片交互</b> - 支持卡片按钮点击
6. <b>🎤 TTS配音</b> - 输入"配音 文本内容"生成语音
7. <b>🎨 AI图像生成</b> - 输入"生图 描述内容"或"AI画图 描述内容"
8. <b>🖼️ 图像风格转换</b> - 直接发送图片进行风格转换

<i>使用示例：</i>
• 配音 你好，这是一段测试语音
• 生图 一只可爱的小猫在花园里玩耍
• AI画图 未来城市的科幻景观
• 直接发送图片 → 自动转换为贺卡风格

<i>架构优势：统一的服务管理，模块化的媒体处理</i>"""

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