"""
消息处理器 (Message Processor)

核心业务逻辑，负责处理各种类型的消息
完全独立于前端平台，可以被任何适配器调用
"""

from typing import Dict, Any, Optional, Tuple, List
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
    response_type: str  # text, image, audio, post, interactive, image_list
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
        from Module.Common.scripts.common import debug_utils

        try:
            debug_utils.log_and_print(
                f"🔄 MessageProcessor开始处理消息 - 类型: {context.message_type}, 用户: {context.user_name}",
                log_level="INFO"
            )

            # 检查事件是否已处理（去重）
            if self._is_duplicate_event(context.event_id):
                debug_utils.log_and_print("📋 重复事件已跳过", log_level="INFO")
                return ProcessResult.no_reply_result()

            # 记录新事件
            self._record_event(context)

            debug_utils.log_and_print(f"📝 开始分发处理 - 消息类型: {context.message_type}", log_level="INFO")

            # 根据消息类型分发处理
            if context.message_type == "text":
                return self._process_text_message(context)
            elif context.message_type == "image":
                return self._process_image_message(context)
            elif context.message_type == "audio":
                return self._process_audio_message(context)
            elif context.message_type == "menu_click":
                debug_utils.log_and_print(f"🎯 处理菜单点击 - 内容: {context.content}", log_level="INFO")
                return self._process_menu_click(context)
            elif context.message_type == "card_action":
                return self._process_card_action(context)
            else:
                return ProcessResult.error_result(f"不支持的消息类型: {context.message_type}")

        except Exception as e:
            debug_utils.log_and_print(f"❌ MessageProcessor处理失败: {str(e)}", log_level="ERROR")
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
        from Module.Common.scripts.common import debug_utils

        event_key = context.content
        debug_utils.log_and_print(f"🔍 分析菜单键: {event_key}", log_level="INFO")

        # 根据菜单键处理不同功能
        if event_key == "get_bili_url":
            debug_utils.log_and_print("📺 处理B站视频推荐菜单", log_level="INFO")
            return self._handle_bili_video_request(context)
        else:
            debug_utils.log_and_print(f"❓ 未知菜单键: {event_key}", log_level="INFO")
            return ProcessResult.success_result("text", {
                "text": f"收到菜单点击：{event_key}，功能开发中..."
            })

    def _handle_bili_video_request(self, context: MessageContext) -> ProcessResult:
        """处理B站视频推荐请求（重构原有get_bili_url功能）"""
        from Module.Common.scripts.common import debug_utils

        try:
            debug_utils.log_and_print("🎬 开始处理B站视频推荐请求", log_level="INFO")

            # 先发送处理中提示
            result = ProcessResult.success_result("text", {
                "text": "正在获取B站视频推荐，请稍候...",
                "next_action": "process_bili_video",
                "user_id": context.user_id
            })

            debug_utils.log_and_print(f"✅ B站视频推荐请求处理完成，next_action: {result.response_content.get('next_action')}", log_level="INFO")
            return result

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频推荐请求处理失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"B站视频推荐请求处理失败: {str(e)}")

    def process_bili_video_async(self, user_id: str) -> ProcessResult:
        """
        异步处理B站视频推荐（由FeishuAdapter调用）
        重构原有的notion服务调用逻辑
        """
        from Module.Common.scripts.common import debug_utils

        try:
            debug_utils.log_and_print(f"🎯 开始异步处理B站视频，用户ID: {user_id}", log_level="INFO")

            if not self.app_controller:
                debug_utils.log_and_print("❌ app_controller不可用", log_level="ERROR")
                return ProcessResult.error_result("系统服务不可用")

            debug_utils.log_and_print("🔍 尝试获取notion服务", log_level="INFO")

            # 尝试获取notion服务（需要在新架构中注册）
            notion_service = self.app_controller.get_service('notion')
            if not notion_service:
                debug_utils.log_and_print("❌ notion服务获取失败", log_level="ERROR")
                return ProcessResult.error_result("抱歉，B站视频推荐服务暂时不可用")

            debug_utils.log_and_print("✅ notion服务获取成功，准备调用get_bili_video", log_level="INFO")

            # 调用notion服务获取B站视频推荐（保持原有逻辑）
            debug_utils.log_and_print("🌐 开始调用notion_service.get_bili_video()...", log_level="INFO")
            video = notion_service.get_bili_video()
            debug_utils.log_and_print(f"📺 notion服务调用完成，结果: {video.get('success', False) if video else 'None'}", log_level="INFO")

            if not video.get("success", False):
                debug_utils.log_and_print("⚠️ 未获取到有效的B站视频", log_level="WARNING")
                return ProcessResult.error_result("暂时没有找到适合的B站视频，请稍后再试")

            debug_utils.log_and_print(f"🎬 获取到视频: {video.get('title', '无标题')}", log_level="INFO")

            # 生成B站视频推荐卡片（重构原有卡片逻辑）
            debug_utils.log_and_print("🎨 开始生成B站视频卡片", log_level="INFO")
            card_content = self._create_bili_video_card(video)
            debug_utils.log_and_print("✅ B站视频卡片生成完成", log_level="INFO")

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频处理异常: {str(e)}", log_level="ERROR")
            import traceback
            debug_utils.log_and_print(f"异常堆栈: {traceback.format_exc()}", log_level="ERROR")
            return ProcessResult.error_result(f"获取B站视频推荐时出现错误，请稍后再试")

    def _create_bili_video_card(self, video: Dict[str, Any], is_read: bool = False) -> Dict[str, Any]:
        """创建B站视频推荐卡片（重构原有BiliVideoHandler._build_bili_card逻辑）"""

        # 构建基础卡片
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                # 视频标题
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📽️ {video.get('title', '无标题视频')}**"
                    }
                },
                # 视频基本信息 - 作者、优先级
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**作者:** {video.get('author', '未知')}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**优先级:** {video.get('chinese_priority', '未知')}"
                            }
                        }
                    ]
                },
                # 视频基本信息 - 时长、来源
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**时长:** {video.get('duration_str', '未知')}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**来源:** {video.get('chinese_source', '未知')}"
                            }
                        }
                    ]
                },
                # 投稿日期
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**投稿日期:** {video.get('upload_date', '未知')}"
                    }
                },
                # 分隔线
                {
                    "tag": "hr"
                },
                # 推荐概要
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**推荐理由:**\n{video.get('summary', '无')}"
                    }
                },
                # 分隔线
                {
                    "tag": "hr"
                },
                # 视频链接 - 创建两个链接，一个用于移动端，一个用于桌面端
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"[🔗 点击观看视频 (移动端)]({self._convert_to_bili_app_link(video.get('url', ''))})\n\n"
                            f"[🔗 点击观看视频 (桌面端)]({video.get('url', '')})"
                        )
                    }
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "📺 B站视频推荐" + (" (已读)" if is_read else "")
                }
            }
        }

        # 只有未读状态才添加"标记为已读"按钮
        if not is_read:
            card["elements"].append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "👍 标记为已读"
                        },
                        "type": "primary",
                        "value": {
                            "action": "mark_bili_read",
                            "pageid": video.get("pageid", "")
                        }
                    }
                ]
            })

        return card

    def _convert_to_bili_app_link(self, web_url: str) -> str:
        """
        将B站网页链接转换为B站应用链接
        （重构原有BiliVideoHandler._convert_to_bili_app_link逻辑）

        Args:
            web_url: B站网页链接

        Returns:
            str: B站应用链接
        """
        # 检查是否是BV号格式
        import re
        bv_match = re.search(r'(/BV[a-zA-Z0-9]+)', web_url)
        if bv_match:
            bv_id = bv_match.group(1).replace('/', '')
            # 构造B站应用链接
            return f"bilibili://video/{bv_id}"

        # 检查是否包含av号
        av_match = re.search(r'av(\d+)', web_url)
        if av_match:
            av_id = av_match.group(1)
            return f"bilibili://video/av{av_id}"

        # 默认返回原始链接
        return web_url

    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片按钮动作（包含mark_bili_read）"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        # 根据动作类型处理
        if action == "mark_bili_read":
            return self._handle_mark_bili_read(context, action_value)
        elif action == "send_alarm":
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

    def _handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理标记B站视频为已读（重构原有MarkBiliReadHandler逻辑）

        Args:
            context: 消息上下文
            action_value: 按钮值，包含pageid

        Returns:
            ProcessResult: 处理结果
        """
        try:
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            # 获取notion服务
            notion_service = self.app_controller.get_service('notion')
            if not notion_service:
                return ProcessResult.error_result("标记服务暂时不可用")

            # 获取页面ID
            pageid = action_value.get("pageid", "")
            if not pageid:
                return ProcessResult.error_result("缺少页面ID，无法标记为已读")

            # 执行标记为已读操作
            success = notion_service.mark_video_as_read(pageid)
            if not success:
                return ProcessResult.error_result("标记失败，请稍后重试")

            # 获取更新后的视频信息
            video = notion_service.get_video_by_id(pageid)
            if not video:
                # 如果无法获取视频信息，只返回成功提示
                return ProcessResult.success_result("card_action_response", {
                    "toast": {
                        "type": "success",
                        "content": "已标记为已读"
                    }
                })

            # 构建更新后的卡片（显示已读状态）
            updated_card = self._create_bili_video_card(video, is_read=True)

            # 返回飞书卡片更新响应格式（按照原有MarkBiliReadHandler格式）
            return ProcessResult.success_result("card_action_response", {
                "toast": {
                    "type": "success",
                    "content": "已标记为已读"
                },
                "card": {
                    "type": "raw",
                    "data": updated_card
                }
            })

        except Exception as e:
            return ProcessResult.error_result(f"标记已读失败: {str(e)}")

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
        help_text = """<b>阶段3 MVP - 音频+图像+定时任务功能</b>

当前支持的功能：
1. <b>基础对话</b> - 发送任意文本消息
2. <b>问候功能</b> - 输入"你好"获得问候回复
3. <b>帮助菜单</b> - 输入"帮助"查看此菜单
4. <b>菜单交互</b> - 支持机器人菜单点击
5. <b>卡片交互</b> - 支持富文本卡片按钮点击
6. <b>🎤 TTS配音</b> - 输入"配音 文本内容"生成语音
7. <b>🎨 AI图像生成</b> - 输入"生图 描述内容"或"AI画图 描述内容"
8. <b>🖼️ 图像风格转换</b> - 直接发送图片进行风格转换
9. <b>📺 B站视频推荐</b> - 点击菜单"B站推荐"获取个性化视频
10. <b>⏰ 定时任务</b> - 日程提醒和B站更新推送（自动执行）

<i>使用示例：</i>
• 配音 你好，这是一段测试语音
• 生图 一只可爱的小猫在花园里玩耍
• AI画图 未来城市的科幻景观
• 直接发送图片 → 自动转换为贺卡风格
• 点击菜单"B站推荐" → 获取个性化视频推荐

<i>定时任务特性：</i>
• 📅 每天07:30自动发送B站信息汇总（包含推荐视频摘要）
• 📺 每天15:30和23:55自动推送B站更新
• 🎯 支持富文本卡片交互，可查看详细信息

<i>架构优势：统一的服务管理，模块化的媒体处理和B站数据分析</i>"""

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

    def _create_daily_schedule_message(self) -> ProcessResult:
        """创建每日信息汇总消息（7:30定时卡片容器）"""
        try:
            # 构建B站信息cache分析数据
            analysis_data = self._build_bilibili_cache_analysis()
            card_content = self._create_daily_summary_card(analysis_data)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            return ProcessResult.error_result(f"创建每日信息汇总失败: {str(e)}")

    def _build_bilibili_cache_analysis(self) -> Dict[str, Any]:
        """
        构建B站信息cache分析数据（整合get_bili_url的数据）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频数据
        if self.app_controller:
            notion_service = self.app_controller.get_service('notion')
            if notion_service:
                try:
                    # 调用和get_bili_url相同的notion服务获取数据
                    video = notion_service.get_bili_video()
                    if video and video.get("success", False):
                        return {
                            "date": now.strftime("%Y年%m月%d日"),
                            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                            "recommended_video": {
                                "title": video.get("title", "")[:30] + "..." if len(video.get("title", "")) > 30 else video.get("title", ""),
                                "author": video.get("author", ""),
                                "chinese_source": video.get("chinese_source", ""),
                                "chinese_priority": video.get("chinese_priority", ""),
                                "available": True
                            },
                            "source": "notion_analysis",
                            "timestamp": now.isoformat()
                        }
                except Exception as e:
                    from Module.Common.scripts.common import debug_utils
                    debug_utils.log_and_print(f"获取notion B站数据失败: {e}", log_level="WARNING")

        # 基础状态信息作为fallback
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "status": "notion服务B站数据获取中...",
            "source": "placeholder",
            "timestamp": now.isoformat()
        }

    def _create_daily_summary_card(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        source = analysis_data.get('source', 'unknown')

        if source == 'notion_analysis':
            # notion服务提供的B站分析数据
            content = self._format_notion_bili_analysis(analysis_data)
        else:
            # 占位信息
            content = f"📊 **{analysis_data['date']} {analysis_data['weekday']}** \\n\\n🔄 **系统状态**\\n\\n{analysis_data.get('status', '服务准备中...')}"

        return {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": content,
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "📋 **每日信息汇总**\\n\\n数据来源：B站信息cache分析系统",
                        "tag": "lark_md"
                    }
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "📊 每日信息汇总",
                    "tag": "plain_text"
                }
            }
        }

    def _format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站分析数据"""
        content = f"📊 **{data['date']} {data['weekday']}** \\n\\n🎯 **B站信息分析汇总**\\n\\n"

        # 推荐视频信息部分
        recommended_video = data.get('recommended_video')
        if recommended_video and recommended_video.get('available'):
            content += "🎬 **今日推荐视频:**\\n"
            content += f"• 标题: {recommended_video.get('title', '未知')}\\n"
            content += f"• 作者: {recommended_video.get('author', '未知')}\\n"
            content += f"• 来源: {recommended_video.get('chinese_source', '未知')}\\n"
            content += f"• 优先级: {recommended_video.get('chinese_priority', '未知')}\\n\\n"
        else:
            content += "🎬 **今日推荐视频:** 暂无可用推荐\\n\\n"

        content += "💡 **使用提示:** 点击菜单中的\"B站推荐\"获取详细视频信息"

        return content

    # ================ 定时任务消息生成方法 ================

    def create_scheduled_message(self, message_type: str, **kwargs) -> ProcessResult:
        """
        创建定时任务消息（供SchedulerService调用）

        Args:
            message_type: 消息类型 ('daily_schedule', 'bilibili_updates')
            **kwargs: 消息相关参数

        Returns:
            ProcessResult: 包含富文本卡片的处理结果
        """
        try:
            if message_type == "daily_schedule":
                return self._create_daily_schedule_message()

            elif message_type == "bilibili_updates":
                sources = kwargs.get('sources', None)
                return self._create_bilibili_updates_message(sources)

            else:
                return ProcessResult.error_result(f"不支持的定时消息类型: {message_type}")

        except Exception as e:
            return ProcessResult.error_result(f"创建定时消息失败: {str(e)}")

    def _create_bilibili_updates_message(self, sources: Optional[List[str]] = None) -> ProcessResult:
        """创建B站更新提醒消息"""
        try:
            # 生成B站更新通知卡片
            card_content = self._create_bilibili_updates_card(sources)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            return ProcessResult.error_result(f"创建B站更新提醒失败: {str(e)}")

    def _create_bilibili_updates_card(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """创建B站更新通知卡片"""
        source_text = "、".join(sources) if sources else "全部源"
        now = datetime.now()

        return {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": f"📺 **B站内容更新通知**\\n\\n🔄 数据源：{source_text}\\n⏰ 处理时间：{now.strftime('%H:%M')}\\n\\n✅ 服务端已完成内容处理和更新",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**📋 处理完成**\\n\\n系统已自动处理B站数据源，新内容已添加到数据库。\\n可通过B站服务端API或相关应用查看具体更新内容。",
                        "tag": "lark_md"
                    }
                }
            ],
            "header": {
                "template": "red",
                "title": {
                    "content": "📺 B站更新完成",
                    "tag": "plain_text"
                }
            }
        }