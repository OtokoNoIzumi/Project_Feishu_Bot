"""
新的消息处理器 (Message Processor)

重构后的核心业务逻辑，使用子处理器模式
完全独立于前端平台，可以被任何适配器调用
"""

from typing import Dict, Any
from .processors import (
    BaseProcessor, MessageContext, ProcessResult,
    TextProcessor, MediaProcessor, BilibiliProcessor,
    AdminProcessor, ScheduleProcessor
)
from Module.Common.scripts.common import debug_utils


class MessageProcessor(BaseProcessor):
    """
    重构后的消息处理器

    职责：
    1. 接收标准化的消息上下文
    2. 分发到对应的子处理器
    3. 返回标准化的处理结果
    """

    def __init__(self, app_controller=None):
        """
        初始化消息处理器

        Args:
            app_controller: 应用控制器，用于访问各种服务
        """
        super().__init__(app_controller)

        # 初始化子处理器
        self.text_processor = TextProcessor(app_controller)
        self.media_processor = MediaProcessor(app_controller)
        self.bilibili_processor = BilibiliProcessor(app_controller)
        self.admin_processor = AdminProcessor(app_controller)
        self.schedule_processor = ScheduleProcessor(app_controller)

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
                debug_utils.log_and_print("📋 重复事件已跳过", log_level="INFO")
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
            debug_utils.log_and_print(f"❌ 消息处理失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"消息处理失败: {str(e)}")

    def _process_text_message(self, context: MessageContext) -> ProcessResult:
        """处理文本消息"""
        user_msg = context.content

        # 管理员配置更新指令
        if self.admin_processor.is_admin_command(user_msg):
            content = self._extract_command_content(user_msg, [self.admin_processor.get_update_trigger()])
            self._log_command(context.user_name, "🔧", "触发配置更新指令", content)
            return self.admin_processor.handle_config_update(context, user_msg)

        # TTS配音指令
        if "配音" in user_msg:
            content = self._extract_command_content(user_msg, ["配音"])
            self._log_command(context.user_name, "🎤", "触发TTS配音指令", content)
            return self.media_processor.handle_tts_command(context, user_msg)

        # 图像生成指令
        if "生图" in user_msg or "AI画图" in user_msg:
            content = self._extract_command_content(user_msg, ["生图", "AI画图"])
            self._log_command(context.user_name, "🎨", "触发图像生成指令", content)
            return self.media_processor.handle_image_generation_command(context, user_msg)

        # 富文本指令
        if "富文本" in user_msg:
            self._log_command(context.user_name, "📄", "触发富文本指令")
            return self.media_processor.handle_rich_text_command(context)

        # 图片/壁纸指令
        if "图片" in user_msg or "壁纸" in user_msg:
            self._log_command(context.user_name, "🖼️", "触发图片指令")
            return self.media_processor.handle_sample_image_command(context)

        # B站/视频指令（触发菜单效果）
        if "B站" in user_msg or "视频" in user_msg:
            content = self._extract_command_content(user_msg, ["B站", "视频"])
            self._log_command(context.user_name, "📺", "触发B站视频指令", content if content else None)
            return self.bilibili_processor.handle_bili_text_command(context)

        # 基础指令处理
        if "帮助" in user_msg:
            self._log_command(context.user_name, "❓", "查看帮助")
            return self.text_processor.handle_help_command(context)
        elif "你好" in user_msg:
            self._log_command(context.user_name, "👋", "发送问候")
            return self.text_processor.handle_greeting_command(context)
        else:
            # 默认回复
            return self.text_processor.handle_default_message(context)

    def _process_image_message(self, context: MessageContext) -> ProcessResult:
        """处理图片消息 - 图像风格转换"""
        return self.media_processor.handle_image_message(context)

    def _process_audio_message(self, context: MessageContext) -> ProcessResult:
        """处理音频消息"""
        return self.media_processor.handle_audio_message(context)

    def _process_menu_click(self, context: MessageContext) -> ProcessResult:
        """处理菜单点击"""
        return self.bilibili_processor.handle_menu_click(context)

    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片按钮动作"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        # 根据动作类型处理
        if action == "mark_bili_read":
            return self._handle_mark_bili_read(context, action_value)
        else:
            return ProcessResult.success_result("text", {
                "text": f"收到卡片动作：{action}，功能开发中..."
            })

    def _handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理标记B站视频为已读
        根据卡片类型分发到对应的处理器
        """
        try:
            card_type = action_value.get("card_type", "menu")

            if card_type == "daily":
                # 定时卡片由ScheduleProcessor处理
                return self.schedule_processor.handle_mark_bili_read(context, action_value)
            else:
                # 菜单卡片由BilibiliProcessor处理
                return self.bilibili_processor.handle_mark_bili_read(context, action_value)

        except Exception as e:
            debug_utils.log_and_print(f"❌ 标记B站视频为已读失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"处理失败：{str(e)}")

    # ================ 异步处理方法（供适配器调用）================

    def process_bili_video_async(self, user_id: str) -> ProcessResult:
        """异步处理B站视频推荐（由FeishuAdapter调用）"""
        return self.bilibili_processor.process_bili_video_async(user_id)

    def process_tts_async(self, tts_text: str) -> ProcessResult:
        """异步处理TTS生成（由FeishuAdapter调用）"""
        return self.media_processor.process_tts_async(tts_text)

    def process_image_generation_async(self, prompt: str) -> ProcessResult:
        """异步处理图像生成（由FeishuAdapter调用）"""
        return self.media_processor.process_image_generation_async(prompt)

    def process_image_conversion_async(self, image_base64: str, mime_type: str,
                                     file_name: str, file_size: int) -> ProcessResult:
        """异步处理图像风格转换（由FeishuAdapter调用）"""
        return self.media_processor.process_image_conversion_async(
            image_base64, mime_type, file_name, file_size
        )

    # ================ 定时任务方法（供SchedulerService调用）================

    def create_scheduled_message(self, message_type: str, **kwargs) -> ProcessResult:
        """创建定时任务消息（供SchedulerService调用）"""
        return self.schedule_processor.create_scheduled_message(message_type, **kwargs)

    # ================ 状态查询方法 ================

    def get_status(self) -> Dict[str, Any]:
        """获取消息处理器状态"""
        return {
            "processor_type": "modular",
            "sub_processors": {
                "text": "TextProcessor",
                "media": "MediaProcessor",
                "bilibili": "BilibiliProcessor",
                "admin": "AdminProcessor",
                "schedule": "ScheduleProcessor"
            },
            "app_controller_available": self.app_controller is not None,
            "supported_message_types": ["text", "image", "audio", "menu_click", "card_action"]
        }