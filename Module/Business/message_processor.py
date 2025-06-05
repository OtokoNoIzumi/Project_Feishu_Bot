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
            config_service = self.app_controller.get_service('config')
            if config_service:
                # 获取管理员ID - 优先从环境变量获取
                self.admin_id = config_service.get_env("ADMIN_ID", "")
                if not self.admin_id:
                    # 如果环境变量没有，尝试从配置文件获取
                    self.admin_id = config_service.get("admin_id", "")

                # 获取更新触发器配置
                self.update_config_trigger = config_service.get("update_config_trigger", "whisk令牌")
            else:
                # 配置服务不可用，使用默认值
                self.admin_id = ''
                self.update_config_trigger = 'whisk令牌'
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

        # 富文本指令
        if "富文本" in user_msg:
            return self._handle_rich_text_command(context)

        # 图片/壁纸指令
        if "图片" in user_msg or "壁纸" in user_msg:
            return self._handle_sample_image_command(context)

        # B站/视频指令（触发菜单效果）
        if "B站" in user_msg or "视频" in user_msg:
            return self._handle_bili_text_command(context)

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
            # 检查缓存状态，决定是否需要发送提示消息
            need_cache_sync = False
            cache_status_msg = "正在获取B站视频推荐，请稍候..."

            if self.app_controller:
                notion_service = self.app_controller.get_service('notion')
                if notion_service:
                    # 检查缓存是否需要更新
                    if not notion_service._is_cache_valid() or not notion_service.cache_data.get(notion_service.bili_cache_key):
                        need_cache_sync = True
                        cache_status_msg = "正在从Notion同步最新数据，首次获取可能需要较长时间，请稍候..."
                        debug_utils.log_and_print("📋 检测到缓存过期，将执行数据同步", log_level="INFO")

            # 只有在需要同步缓存时才发送提示消息
            if need_cache_sync:
                result = ProcessResult.success_result("text", {
                    "text": cache_status_msg,
                    "next_action": "process_bili_video",
                    "user_id": context.user_id
                })
                debug_utils.log_and_print("📤 发送数据同步提示消息", log_level="INFO")
            else:
                # 直接返回异步处理指令，不发送提示消息
                result = ProcessResult.success_result("text", {
                    "text": "",  # 空文本，不显示
                    "next_action": "process_bili_video",
                    "user_id": context.user_id
                })
                debug_utils.log_and_print("⚡ 缓存有效，跳过提示消息直接处理", log_level="INFO")

            debug_utils.log_and_print(f"✅ B站视频推荐请求处理完成，next_action: {result.response_content.get('next_action')}", log_level="INFO")
            return result

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频推荐请求处理失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"B站视频推荐请求处理失败: {str(e)}")

    def process_bili_video_async(self, user_id: str) -> ProcessResult:
        """
        异步处理B站视频推荐（由FeishuAdapter调用）
        重构原有的notion服务调用逻辑，现在支持1+3模式
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

            debug_utils.log_and_print("✅ notion服务获取成功，准备调用get_bili_videos_multiple", log_level="INFO")

            # 调用notion服务获取多个B站视频推荐（1+3模式）
            debug_utils.log_and_print("🌐 开始调用notion_service.get_bili_videos_multiple()...", log_level="INFO")
            videos_data = notion_service.get_bili_videos_multiple()
            debug_utils.log_and_print(f"📺 notion服务调用完成，结果: {videos_data.get('success', False) if videos_data else 'None'}", log_level="INFO")

            if not videos_data.get("success", False):
                debug_utils.log_and_print("⚠️ 未获取到有效的B站视频", log_level="WARNING")
                return ProcessResult.error_result("暂时没有找到适合的B站视频，请稍后再试")

            main_video = videos_data.get("main_video", {})
            additional_videos = videos_data.get("additional_videos", [])

            debug_utils.log_and_print(
                f"🎬 获取到主视频: {main_video.get('title', '无标题')}, " +
                f"额外视频: {len(additional_videos)}个",
                log_level="INFO"
            )

            # 生成B站视频推荐卡片（1+3模式）

            card_content = self._create_bili_video_card_multiple(main_video, additional_videos)


            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频处理异常: {str(e)}", log_level="ERROR")
            import traceback
            debug_utils.log_and_print(f"异常堆栈: {traceback.format_exc()}", log_level="ERROR")
            return ProcessResult.error_result(f"获取B站视频推荐时出现错误，请稍后再试")

    def _create_bili_video_card_multiple(self, main_video: Dict[str, Any], additional_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建B站视频推荐卡片（1+3模式）"""

        # 获取notion服务以检查已读状态
        notion_service = None
        if self.app_controller:
            notion_service = self.app_controller.get_service('notion')

        # 检查主视频是否已读
        main_video_pageid = main_video.get("pageid", "")
        main_video_read = notion_service.is_video_read(main_video_pageid) if notion_service and main_video_pageid else False
        main_video_title = main_video.get('title', '无标题视频')
        if main_video_read:
            main_video_title += " | 已读"

        # 构建基础卡片
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                # 主视频标题（包含已读状态）
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📽️ {main_video_title}**"
                    }
                },
                # 主视频基本信息 - 优先级、时长、来源（紧凑显示）
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**优先级:** {main_video.get('chinese_priority', '未知')} | **时长:** {main_video.get('duration_str', '未知')} | **作者:** {main_video.get('author', '未知')} | **来源:** {main_video.get('chinese_source', '未知')} | **投稿日期:** {main_video.get('upload_date', '未知')}"
                    }
                },
                # 主视频推荐概要（简化版）
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**推荐理由:** {main_video.get('summary', '无')[:50]}{'...' if len(main_video.get('summary', '')) > 50 else ''}"
                    }
                },
                # 主视频链接和已读按钮
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📱 手机"
                            },
                            "type": "default",
                            "size": "tiny",
                            "url": self._convert_to_bili_app_link(main_video.get('url', ''))
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "💻 电脑"
                            },
                            "type": "default",
                            "size": "tiny",
                            "url": main_video.get('url', '')
                        }
                    ] + ([] if main_video_read else [{
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✅ 已读"
                        },
                        "type": "primary",
                        "size": "tiny",
                        "value": {
                            "action": "mark_bili_read",
                            "pageid": main_video.get("pageid", ""),
                            "card_type": "menu",  # 菜单推送卡片
                            "video_index": 0,  # 主视频序号
                            # 保存原视频数据用于卡片重构
                            "original_main_video": main_video,
                            "original_additional_videos": additional_videos
                        }
                    }])
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "📺 B站视频推荐"
                }
            }
        }

        # 如果有额外视频，添加额外推荐部分（简化版）
        if additional_videos:
            # 添加额外推荐标题
            card["elements"].extend([
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**📋 更多推荐**"
                    }
                }
            ])

            # 添加每个额外视频的简化展示
            for i, video in enumerate(additional_videos, 1):
                # 检查该视频是否已读
                video_pageid = video.get('pageid', '')
                video_read = notion_service.is_video_read(video_pageid) if notion_service and video_pageid else False

                # 视频标题（兼容新旧字段）
                title = video.get('标题', video.get('title', '无标题视频'))
                if len(title) > 30:
                    title = title[:30] + "..."

                # 兼容新旧字段格式
                priority = video.get('优先级', video.get('chinese_priority', '未知'))
                duration = video.get('时长', video.get('duration_str', '未知'))

                card["elements"].append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}"
                    }
                })

                # 额外视频的操作按钮（一行显示）
                desktop_url = video.get('url', '')
                mobile_url = self._convert_to_bili_app_link(desktop_url)  # 转换为B站应用链接
                pageid = video.get('pageid', '')

                # 使用action_layout实现按钮一行显示
                card["elements"].append({
                    "tag": "action",
                    "layout": "flow",  # 使用flow布局让按钮在一行显示
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📱 手机"
                            },
                            "type": "default",
                            "size": "tiny",
                            "url": mobile_url
                        } if mobile_url else {},
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "💻 电脑"
                            },
                            "type": "default",
                            "size": "tiny",
                            "url": desktop_url
                        } if desktop_url else {}
                    ] + ([] if video_read else [{
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✅ 已读"
                        },
                        "type": "primary",
                        "size": "tiny",
                        "value": {
                            "action": "mark_bili_read",
                            "pageid": pageid,
                            "card_type": "menu",  # 菜单推送卡片
                            "video_index": i + 1,  # 额外视频序号 (1,2,3)
                            # 保存原视频数据用于卡片重构
                            "original_main_video": main_video,
                            "original_additional_videos": additional_videos
                        }
                    }] if pageid else [])
                })

                # 添加分隔线（最后一个视频除外）
                if i < len(additional_videos) - 1:
                    card["elements"].append({
                        "tag": "hr"
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
        from Module.Common.scripts.common import debug_utils

        try:
            # 输入验证
            if not web_url or not isinstance(web_url, str):
                return web_url or ""

            # 检查是否是BV号格式
            import re
            bv_match = re.search(r'(/BV[a-zA-Z0-9]+)', web_url)
            if bv_match:
                bv_id = bv_match.group(1).replace('/', '')
                return f"bilibili://video/{bv_id}"

            # 检查是否包含av号
            av_match = re.search(r'av(\d+)', web_url)
            if av_match:
                av_id = av_match.group(1)
                return f"bilibili://video/av{av_id}"

            # 默认返回原始链接
            return web_url

        except Exception as e:
            debug_utils.log_and_print(f"[链接转换] 处理异常: {e}, URL: {web_url}", log_level="ERROR")
            return web_url  # 异常时返回原始链接

    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片按钮动作（包含mark_bili_read）"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        # 根据动作类型处理
        if action == "mark_bili_read":
            return self._handle_mark_bili_read(context, action_value)
        # elif action == "send_alarm":
        #     return ProcessResult.success_result("text", {
        #         "text": "🚨 收到告警卡片点击，告警功能将在后续版本实现"
        #     })
        # elif action == "confirm_action":
        #     return ProcessResult.success_result("text", {
        #         "text": "✅ 操作已确认"
        #     })
        else:
            return ProcessResult.success_result("text", {
                "text": f"收到卡片动作：{action}，功能开发中..."
            })

    def _handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理标记B站视频为已读（基于原数据精确重构）

        使用按钮中保存的原视频数据重构卡片，只更新已读状态，避免重新获取数据导致内容替换

        Args:
            context: 消息上下文
            action_value: 按钮值，包含原视频数据和标记信息

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

            # 获取参数
            pageid = action_value.get("pageid", "")
            card_type = action_value.get("card_type", "menu")
            video_index = action_value.get("video_index", 0)

            # 获取原始视频数据
            original_main_video = action_value.get("original_main_video", {})
            original_additional_videos = action_value.get("original_additional_videos", [])

            if not pageid:
                return ProcessResult.error_result("缺少页面ID，无法标记为已读")

            # 执行标记为已读操作
            success = notion_service.mark_video_as_read(pageid)
            if not success:
                return ProcessResult.error_result("标记为已读失败")

            # 根据卡片类型处理
            if card_type == "daily":
                # 定时卡片：基于原始数据重构，只更新已读状态，不重新获取统计数据
                try:
                    original_analysis_data = action_value.get("original_analysis_data")
                    if original_analysis_data:
                        # 使用原始数据重新生成卡片，已读状态会自动更新
                        updated_card = self._create_daily_summary_card(original_analysis_data)
                    else:
                        # 如果没有原始数据，降级处理
                        return ProcessResult.success_result("card_action_response", {
                            "toast": {
                                "type": "success",
                                "content": f"已标记第{video_index + 1}个推荐为已读"
                            }
                        })

                    return ProcessResult.success_result("card_action_response", {
                        "toast": {
                            "type": "success",
                            "content": f"已标记第{video_index + 1}个推荐为已读"
                        },
                        "card": {
                            "type": "raw",
                            "data": updated_card
                        }
                    })
                except Exception as e:
                    # 如果重新生成失败，只返回toast
                    return ProcessResult.success_result("card_action_response", {
                        "toast": {
                            "type": "success",
                            "content": f"已标记第{video_index + 1}个推荐为已读"
                        }
                    })
            else:
                # 菜单卡片：基于原数据重构卡片
                if not original_main_video:
                    # 如果没有原数据，只返回toast
                    return ProcessResult.success_result("card_action_response", {
                        "toast": {
                            "type": "success",
                            "content": f"已标记第{video_index + 1}个视频为已读"
                        }
                    })

                # 重新生成卡片，此时已读状态会自动更新（因为notion_service.is_video_read会返回True）
                updated_card = self._create_bili_video_card_multiple(
                    original_main_video,
                    original_additional_videos
                )

                return ProcessResult.success_result("card_action_response", {
                    "toast": {
                        "type": "success",
                        "content": f"已标记第{video_index + 1}个视频为已读"
                    },
                    "card": {
                        "type": "raw",
                        "data": updated_card
                    }
                })

        except Exception as e:
            from Module.Common.scripts.common import debug_utils
            debug_utils.log_and_print(f"❌ 标记B站视频为已读失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"处理失败：{str(e)}")



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
                f"格式错误，请使用 '{self.update_config_trigger} 变量名 新值' 格式，"
                f"例如：{self.update_config_trigger} cookies xxxx"
            )

        variable_name, new_value = command_parts

        # 检查是否为支持的变量
        supported_variables = ["cookies", "auth_token"]
        if variable_name not in supported_variables:
            return ProcessResult.error_result(
                f"不支持更新变量 '{variable_name}'，"
                f"只能更新: {', '.join(supported_variables)}"
            )

        # 调用配置服务更新配置
        if not self.app_controller:
            return ProcessResult.error_result("系统服务不可用")

        config_service = self.app_controller.get_service('config')
        if not config_service:
            return ProcessResult.error_result("配置服务不可用")

        try:
            # 创建验证器字典
            validators = {
                "cookies": self._verify_cookie,
                "auth_token": self._verify_auth_token
            }

            success, reply_text = config_service.update_config(
                variable_name,
                new_value,
                validators
            )

            return ProcessResult.success_result("text", {
                "text": reply_text
            })

        except Exception as e:
            return ProcessResult.error_result(f"配置更新失败: {str(e)}")

    def _verify_cookie(self, cookie_value: str) -> tuple[bool, str]:
        """验证Cookie格式"""
        if not cookie_value or len(cookie_value.strip()) < 10:
            return False, "Cookie值太短，请检查格式"
        return True, "Cookie格式验证通过"

    def _verify_auth_token(self, auth_token_value: str) -> tuple[bool, str]:
        """验证认证Token格式"""
        if not auth_token_value or len(auth_token_value.strip()) < 10:
            return False, "认证Token值太短，请检查格式"
        return True, "认证Token格式验证通过"

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
        help_text = """<b>🤖 飞书机器人助手 v3.0 - 重构完成版</b>

<b>核心功能：</b>

<b>🔊 AI配音</b>
• 配音 [文本内容] → 生成语音消息

<b>🎨 AI绘图</b>
• 生图 [描述] → AI生成图片
• AI画图 [描述] → AI生成图片

<b>🖼️ 图片处理</b>
• 上传图片 → 自动转换为精美贺卡风格
• 图片/壁纸 → 分享精美示例图片

<b>📺 B站推荐</b>
• 菜单"B站" → 个性化视频推荐（支持1+3模式显示）
• B站/视频 → 快速获取视频推荐

<b>📄 富文本演示</b>
• 富文本 → 展示富文本格式示例

<b>📅 定时功能</b>
• 每天07:30 → 自动推送B站信息汇总
• 每天15:30和23:55 → 自动推送B站更新

<b>💬 基础交互</b>
• 帮助 → 查看功能列表
• 你好 → 问候回复

<b>⚙️ 管理功能</b>
• whisk令牌 [变量名] [新值] → 更新配置（管理员专用）

<i>使用示例：</i>
• 配音 你好，这是一段测试语音
• 生图 一只可爱的小猫在花园里玩耍
• AI画图 未来城市的科幻景观
• 富文本 → 查看富文本格式演示
• 图片 → 获取精美壁纸
• B站 → 快速视频推荐
• 直接发送图片 → 自动转换为贺卡风格
• 点击菜单"B站" → 获取个性化视频推荐

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

    def _handle_rich_text_command(self, context: MessageContext) -> ProcessResult:
        """处理富文本指令"""
        try:
            # 获取示例图片路径
            import os
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在，无法创建富文本消息")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            # 生成富文本内容
            rich_text_content = {
                "zh_cn": {
                    "title": "富文本示例",
                    "content": [
                        [
                            {"tag": "text", "text": "第一行:", "style": ["bold", "underline"]},
                            {"tag": "a", "href": "https://open.feishu.cn", "text": "飞书开放平台", "style": ["italic"]},
                            {"tag": "at", "user_id": "all", "style": ["lineThrough"]}
                        ],
                        [{"tag": "text", "text": "代码示例:"}],
                        [{"tag": "code_block", "language": "PYTHON", "text": "print('Hello World')"}],
                        [{"tag": "hr"}],
                        [{"tag": "md", "text": "**Markdown内容**\n- 列表项1\n- 列表项2\n```python\nprint('代码块')\n```"}]
                    ]
                }
            }

            return ProcessResult.success_result("rich_text", {
                "rich_text_content": rich_text_content,
                "sample_image_data": image_data,
                "sample_image_name": os.path.basename(sample_pic_path)
            })

        except Exception as e:
            return ProcessResult.error_result(f"富文本指令处理失败: {str(e)}")

    def _handle_sample_image_command(self, context: MessageContext) -> ProcessResult:
        """处理图片/壁纸指令"""
        try:
            # 获取示例图片路径
            import os
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            return ProcessResult.success_result("image", {
                "image_data": image_data,
                "image_name": os.path.basename(sample_pic_path)
            })

        except Exception as e:
            return ProcessResult.error_result(f"图片指令处理失败: {str(e)}")

    def _handle_bili_text_command(self, context: MessageContext) -> ProcessResult:
        """处理B站/视频文本指令（等同于菜单点击get_bili_url）"""
        try:
            # 直接复用菜单点击的B站处理逻辑
            return self._handle_bili_video_request(context)

        except Exception as e:
            return ProcessResult.error_result(f"B站视频指令处理失败: {str(e)}")

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
        构建B站信息cache分析数据（获取统计信息用于7:30定时任务）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频统计数据
        if self.app_controller:
            notion_service = self.app_controller.get_service('notion')
            if notion_service:
                try:
                    # 调用统计方法获取B站数据分析
                    stats = notion_service.get_bili_videos_statistics()
                    # 兼容新版返回格式
                    if stats and stats.get("success", False):
                        # 兼容字段映射
                        total_count = stats.get("总未读数", 0)
                        priority_stats = stats.get("优先级统计", {})
                        duration_stats = stats.get("时长分布", {})
                        source_stats = stats.get("来源统计", {})
                        top_recommendations = stats.get("今日精选推荐", [])
                        return {
                            "date": now.strftime("%Y年%m月%d日"),
                            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                            "statistics": {
                                "total_count": total_count,
                                "priority_stats": priority_stats,
                                "duration_stats": duration_stats,
                                "source_stats": source_stats,
                                "top_recommendations": top_recommendations
                            },
                            "source": "notion_statistics",
                            "timestamp": now.isoformat()
                        }
                except Exception as e:
                    from Module.Common.scripts.common import debug_utils
                    debug_utils.log_and_print(f"获取notion B站统计数据失败: {e}", log_level="WARNING")

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

        if source == 'notion_statistics':
            # notion服务提供的B站分析数据
            content = self._format_notion_bili_analysis(analysis_data)
        else:
            # 占位信息
            content = f"📊 **{analysis_data['date']} {analysis_data['weekday']}** \n\n🔄 **系统状态**\n\n{analysis_data.get('status', '服务准备中...')}"

        card = {
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
                # {
                #     "tag": "div",
                #     "text": {
                #         "content": "📋 **每日信息汇总**\n\n数据来源：B站信息cache分析系统",
                #         "tag": "lark_md"
                #     }
                # }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "📊 每日信息汇总",
                    "tag": "plain_text"
                }
            }
        }

        # 如果有推荐视频，添加推荐链接部分
        if source == 'notion_statistics':
            statistics = analysis_data.get('statistics', {})

            # 兼容新版字段名
            top_recommendations = statistics.get('top_recommendations', None)
            if top_recommendations is None:
                top_recommendations = statistics.get('今日精选推荐', [])

            if top_recommendations:
                # 获取notion服务以检查已读状态
                notion_service = None
                if hasattr(self, 'app_controller') and self.app_controller:
                    notion_service = self.app_controller.get_service('notion')

                # 添加推荐视频标题
                card["elements"].extend([
                    # {
                    #     "tag": "hr"
                    # },
                    {
                        "tag": "div",
                        "text": {
                            "content": "🎬 **今日精选推荐**",
                            "tag": "lark_md"
                        }
                    }
                ])

                # 添加每个推荐视频的简化展示
                for i, video in enumerate(top_recommendations, 1):
                    # 检查该视频是否已读（兼容新旧字段）
                    video_pageid = video.get('页面ID', video.get('pageid', ''))
                    video_read = notion_service.is_video_read(video_pageid) if notion_service and video_pageid else False

                    # 视频标题（兼容新旧字段）
                    title = video.get('标题', video.get('title', '无标题视频'))
                    if len(title) > 30:
                        title = title[:30] + "..."

                    # 兼容新旧字段格式
                    priority = video.get('优先级', video.get('chinese_priority', '未知'))
                    duration = video.get('时长', video.get('duration_str', '未知'))

                    card["elements"].append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}"
                        }
                    })

                    # 视频基本信息和链接按钮
                    video_url = video.get('链接', video.get('url', ''))
                    card["elements"].append({
                        "tag": "action",
                        "layout": "flow",  # 使用flow布局让按钮在一行显示
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "📱 手机"
                                },
                                "type": "default",
                                "size": "tiny",
                                "url": self._convert_to_bili_app_link(video_url)
                            },
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "💻 电脑"
                                },
                                "type": "default",
                                "size": "tiny",
                                "url": video_url
                            }
                        ] + ([] if video_read else [{
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 已读"
                            },
                            "type": "primary",
                            "size": "tiny",
                            "value": {
                                "action": "mark_bili_read",
                                "pageid": video_pageid,
                                "card_type": "daily",  # 定时卡片
                                "video_index": i - 1,  # 推荐视频序号 (0,1,2)
                                # 保存原始完整数据用于卡片重构（不重新获取统计数据）
                                "original_analysis_data": analysis_data
                            }
                        }] if video_pageid else [])
                    })

        return card

    def _format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站统计数据"""
        content = f"📊 **{data['date']} {data['weekday']}**"
        content += "\n\n🎯 **B站信息分析汇总**"

        statistics = data.get('statistics', {})

        # 总体统计
        total_count = statistics.get('total_count', None)
        # 兼容新版字段
        if total_count is None:
            total_count = statistics.get('总未读数', 0)
        content += f"\n\n📈 **总计:** {total_count} 个未读视频"

        if total_count > 0:
            # 优先级统计（增加时长总计）
            priority_stats = statistics.get('priority_stats', None)
            if priority_stats is None:
                priority_stats = statistics.get('优先级统计', {})
            if priority_stats:
                content += "\n\n🎯 **优先级分布:**"
                for priority, info in priority_stats.items():
                    # 新版格式：{'😜中': {'数量': 1, '总时长分钟': 51}}
                    count = info.get('数量', info.get('count', 0))
                    total_minutes = info.get('总时长分钟', info.get('total_minutes', 0))
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    content += f"\n• {priority}: {count} 个 ({time_str})"

            # 时长分布
            duration_stats = statistics.get('duration_stats', None)
            if duration_stats is None:
                duration_stats = statistics.get('时长分布', {})
            if duration_stats:
                content += "\n\n⏱️ **时长分布:**"
                for duration_type, count in duration_stats.items():
                    content += f"\n• {duration_type}: {count} 个"

            # 来源统计
            source_stats = statistics.get('source_stats', None)
            if source_stats is None:
                source_stats = statistics.get('来源统计', {})
            if source_stats:
                content += "\n\n📺 **来源分布:**"
                for source, count in source_stats.items():
                    content += f"\n• {source}: {count} 个"

        # 推荐视频链接（如果有）
        # recommendations = statistics.get('top_recommendations', None)
        # if recommendations is None:
        #     recommendations = statistics.get('今日精选推荐', [])
        # if recommendations:
        #     content += "\n\n🔥 **今日精选推荐:**"
        #     for i, video in enumerate(recommendations[:3], 1):
        #         # 新版字段
        #         title = video.get('标题', video.get('title', '无标题'))
        #         if len(title) > 20:
        #             title = title[:20] + "..."
        #         priority = video.get('优先级', video.get('priority', '未知'))
        #         content += f"\n{i}. **{title}** ({priority})"

        # content += "\n\n💡 **使用提示:** 点击菜单中的\"B站推荐\"获取详细视频信息"

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
                api_result = kwargs.get('api_result', None)
                return self._create_bilibili_updates_message(sources, api_result)

            else:
                return ProcessResult.error_result(f"不支持的定时消息类型: {message_type}")

        except Exception as e:
            return ProcessResult.error_result(f"创建定时消息失败: {str(e)}")

    def _create_bilibili_updates_message(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> ProcessResult:
        """创建B站更新提醒消息"""
        try:
            # 生成B站更新通知卡片，传入API结果数据
            card_content = self._create_bilibili_updates_card(sources, api_result)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            return ProcessResult.error_result(f"创建B站更新提醒失败: {str(e)}")

    def _create_bilibili_updates_card(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建B站更新通知卡片（增强版，使用飞书卡片图表组件）"""
        source_text = "、".join(sources) if sources else "全部源"
        now = datetime.now()

        # 基础卡片结构
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "content": "📺 B站数据处理完成",
                    "tag": "plain_text"
                }
            },
            "elements": []
        }

        # 添加基础信息
        card["elements"].extend([
            {
                "tag": "div",
                "text": {
                    "content": f"🔄 **数据源：** {source_text}\n⏰ **处理时间：** {now.strftime('%Y-%m-%d %H:%M:%S')}",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "hr"
            }
        ])

        # 如果有API结果数据，展示详细统计
        if api_result and api_result.get('success') and api_result.get('data'):
            data = api_result['data']

            # 处理统计信息
            if 'processing_stats' in data:
                stats = data['processing_stats']
                total_videos = data.get('total_videos', 0)
                total_minutes = stats.get('total_minutes', 0)

                # 总体统计
                hours = total_minutes // 60
                minutes = total_minutes % 60
                time_display = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

                card["elements"].append({
                    "tag": "div",
                    "text": {
                        "content": f"📊 **总体统计：** {total_videos} 个视频，总时长 {time_display}",
                        "tag": "lark_md"
                    }
                })

                # 优先级分布（使用饼图）
                if 'priority_stats' in stats and total_videos > 0:
                    priority_stats = stats['priority_stats']

                    # 定义优先级排序（确保按High→Medium→Low→None顺序显示）
                    priority_order = ['😍高', '😜中', '😐低', '😶无']
                    # 也支持英文优先级名
                    priority_order_en = ['High', 'Medium', 'Low', 'None']

                    # 构建饼图数据（官方格式，按优先级排序）
                    chart_data = []

                    # 按照定义的顺序处理优先级
                    all_priorities = list(priority_stats.keys())
                    ordered_priorities = []

                    # 先添加预定义顺序中存在的优先级
                    for priority in priority_order + priority_order_en:
                        if priority in all_priorities:
                            ordered_priorities.append(priority)
                            all_priorities.remove(priority)

                    # 再添加其他未预定义的优先级
                    ordered_priorities.extend(all_priorities)

                    for priority in ordered_priorities:
                        if priority in priority_stats:
                            info = priority_stats[priority]
                            count = info.get('count', 0)
                            total_mins = info.get('total_minutes', 0)
                            percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                            # 时长格式化
                            p_hours = total_mins // 60
                            p_minutes = total_mins % 60
                            p_time_display = f"{p_hours}h{p_minutes}m" if p_hours > 0 else f"{p_minutes}m"

                            chart_data.append({
                                "type": f"{priority} {percentage}%",
                                "value": str(count)
                            })

                    # 添加优先级分布饼图
                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "🎯 **优先级分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "优先级分布"
                                },
                                "data": {
                                    "values": chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 类型分布（使用环状图）
                if 'category_stats' in stats and total_videos > 0:
                    category_stats = stats['category_stats']

                    # 构建环状图数据（官方格式，添加百分比）
                    category_chart_data = []
                    for category, info in category_stats.items():
                        count = info.get('count', 0)
                        total_mins = info.get('total_minutes', 0)
                        percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                        c_hours = total_mins // 60
                        c_minutes = total_mins % 60
                        c_time_display = f"{c_hours}h{c_minutes}m" if c_hours > 0 else f"{c_minutes}m"

                        category_chart_data.append({
                            "type": f"{category} {percentage}%",
                            "value": str(count)
                        })

                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "📂 **类型分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "类型分布"
                                },
                                "data": {
                                    "values": category_chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "innerRadius": 0.3,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 新旧视频分布（使用对比饼图）
                if 'new_old_stats' in stats:
                    new_old = stats['new_old_stats']
                    new_count = new_old.get('new_videos', 0)
                    old_count = new_old.get('old_videos', 0)
                    new_minutes = new_old.get('new_total_minutes', 0)
                    old_minutes = new_old.get('old_total_minutes', 0)

                    if new_count + old_count > 0:
                        total_count = new_count + old_count
                        new_percentage = round((new_count / total_count) * 100, 1) if total_count > 0 else 0
                        old_percentage = round((old_count / total_count) * 100, 1) if total_count > 0 else 0

                        new_old_data = [
                            {
                                "type": f"新视频(48h内) {new_percentage}%",
                                "value": str(new_count)
                            },
                            {
                                "type": f"旧视频(48h外) {old_percentage}%",
                                "value": str(old_count)
                            }
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "🕒 **新旧视频分布**",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "新旧视频分布"
                                    },
                                    "data": {
                                        "values": new_old_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                # 广告检测统计（使用对比饼图）
                if 'ad_timestamp_stats' in stats:
                    ad_stats = stats['ad_timestamp_stats']
                    ad_count = ad_stats.get('videos_with_ads', 0)
                    no_ad_count = ad_stats.get('videos_without_ads', 0)
                    ad_percentage_global = ad_stats.get('ads_percentage', 0)
                    avg_ad_duration = ad_stats.get('avg_ad_duration_seconds', 0)

                    if ad_count + no_ad_count > 0:
                        total_ad_count = ad_count + no_ad_count
                        ad_percentage = round((ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0
                        no_ad_percentage = round((no_ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0

                        ad_data = [
                            {"type": f"含广告 {ad_percentage}%", "value": str(ad_count)},
                            {"type": f"无广告 {no_ad_percentage}%", "value": str(no_ad_count)}
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": f"📺 **广告检测** (检测到{ad_percentage_global:.1f}%包含广告)",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "广告检测分布"
                                    },
                                    "data": {
                                        "values": ad_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                        if avg_ad_duration > 0:
                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"💡 平均广告时长: {int(avg_ad_duration)}秒",
                                    "tag": "lark_md"
                                }
                            })

                # 作者排行（文本显示，图表对名字太长不友好）
                if 'author_stats' in stats and stats['author_stats']:
                    author_stats = stats['author_stats'][:5]  # 只显示前5名
                    if author_stats:
                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "👤 **作者排行** (前5名)",
                                    "tag": "lark_md"
                                }
                            }
                        ])

                        for i, author in enumerate(author_stats, 1):
                            name = author.get('name', '未知')
                            count = author.get('count', 0)
                            total_mins = author.get('total_minutes', 0)
                            a_time_display = f"{total_mins//60}h{total_mins%60}m" if total_mins//60 > 0 else f"{total_mins}m"

                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"{i}. **{name}:** {count}个视频 ({a_time_display})",
                                    "tag": "lark_md"
                                }
                            })

            # 显示处理结果概要
            card["elements"].extend([
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "💡 点击菜单中的\"B站\"获取最新无广告的视频",
                        "tag": "lark_md"
                    }
                }
            ])
        else:
            # 没有详细数据时的简化显示
            card["elements"].append({
                "tag": "div",
                "text": {
                    "content": "**📋 处理完成**\n\n系统已自动处理B站数据源，新内容已添加到数据库。\n可通过B站服务端API或相关应用查看具体更新内容。",
                    "tag": "lark_md"
                }
            })

        return card