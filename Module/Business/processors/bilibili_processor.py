"""
B站处理器

处理B站视频推荐、卡片生成、已读标记等功能
"""

import re
from typing import Dict, Any, List
from .base_processor import BaseProcessor, MessageContext, ProcessResult
from Module.Common.scripts.common import debug_utils


class BilibiliProcessor(BaseProcessor):
    """
    B站处理器

    处理B站相关的所有功能
    """

    def handle_bili_video_request(self, context: MessageContext) -> ProcessResult:
        """处理B站视频推荐请求（重构原有get_bili_url功能）"""
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

            # 只有在需要同步缓存时才发送提示消息
            if need_cache_sync:
                result = ProcessResult.success_result("text", {
                    "text": cache_status_msg,
                    "next_action": "process_bili_video",
                    "user_id": context.user_id
                })
            else:
                # 直接返回异步处理指令，不发送提示消息
                result = ProcessResult.success_result("text", {
                    "text": "",  # 空文本，不显示
                    "next_action": "process_bili_video",
                    "user_id": context.user_id
                })

            return result

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频推荐请求处理失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"B站视频推荐请求处理失败: {str(e)}")

    def process_bili_video_async(self, user_id: str) -> ProcessResult:
        """
        异步处理B站视频推荐（由FeishuAdapter调用）
        重构原有的notion服务调用逻辑，现在支持1+3模式
        """
        try:
            if not self.app_controller:
                debug_utils.log_and_print("❌ app_controller不可用", log_level="ERROR")
                return ProcessResult.error_result("系统服务不可用")

            # 尝试获取notion服务（需要在新架构中注册）
            notion_service = self.app_controller.get_service('notion')
            if not notion_service:
                debug_utils.log_and_print("❌ notion服务获取失败", log_level="ERROR")
                return ProcessResult.error_result("抱歉，B站视频推荐服务暂时不可用")

            # 调用notion服务获取多个B站视频推荐（1+3模式）
            videos_data = notion_service.get_bili_videos_multiple()

            if not videos_data.get("success", False):
                debug_utils.log_and_print("⚠️ 未获取到有效的B站视频", log_level="WARNING")
                return ProcessResult.error_result("暂时没有找到适合的B站视频，请稍后再试")

            main_video = videos_data.get("main_video", {})
            additional_videos = videos_data.get("additional_videos", [])

            # 生成B站视频推荐卡片（1+3模式）
            card_content = self.create_bili_video_card_multiple(main_video, additional_videos)

            return ProcessResult.success_result("interactive", card_content)

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频处理异常: {str(e)}", log_level="ERROR")
            import traceback
            debug_utils.log_and_print(f"异常堆栈: {traceback.format_exc()}", log_level="ERROR")
            return ProcessResult.error_result(f"获取B站视频推荐时出现错误，请稍后再试")

    def create_bili_video_card_multiple(self, main_video: Dict[str, Any], additional_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                            "url": self.convert_to_bili_app_link(main_video.get('url', ''))
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
                mobile_url = self.convert_to_bili_app_link(desktop_url)  # 转换为B站应用链接
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
                            "video_index": i,  # 额外视频序号 (1,2,3)
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

    def convert_to_bili_app_link(self, web_url: str) -> str:
        """
        将B站网页链接转换为B站应用链接
        （重构原有BiliVideoHandler._convert_to_bili_app_link逻辑）

        Args:
            web_url: B站网页链接

        Returns:
            str: B站应用链接
        """
        try:
            # 输入验证
            if not web_url or not isinstance(web_url, str):
                return web_url or ""

            # 检查是否是BV号格式
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

    def handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理菜单卡片中的标记B站视频为已读（基于原数据精确重构）

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
            updated_card = self.create_bili_video_card_multiple(
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
            debug_utils.log_and_print(f"❌ 标记B站视频为已读失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"处理失败：{str(e)}")

    def handle_bili_text_command(self, context: MessageContext) -> ProcessResult:
        """处理B站/视频文本指令（等同于菜单点击get_bili_url）"""
        try:
            # 直接复用菜单点击的B站处理逻辑
            return self.handle_bili_video_request(context)

        except Exception as e:
            return ProcessResult.error_result(f"B站视频指令处理失败: {str(e)}")

    def handle_menu_click(self, context: MessageContext) -> ProcessResult:
        """处理菜单点击"""
        event_key = context.content

        # 根据菜单键处理不同功能
        if event_key == "get_bili_url":
            debug_utils.log_and_print(f"📺 B站视频推荐 by [{context.user_name}]", log_level="INFO")
            return self.handle_bili_video_request(context)
        else:
            debug_utils.log_and_print(f"❓ 未知菜单键: {event_key}", log_level="INFO")
            return ProcessResult.success_result("text", {
                "text": f"收到菜单点击：{event_key}，功能开发中..."
            })