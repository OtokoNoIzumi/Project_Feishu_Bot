"""
B站处理器

处理B站视频推荐、卡片生成、已读标记等功能
"""

import re
import json
from typing import Dict, Any, List
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute
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

    @require_service('notion', "抱歉，B站视频推荐服务暂时不可用")
    @safe_execute("获取B站视频推荐时出现错误，请稍后再试")
    def process_bili_video_async(self, cached_data: Dict[str, Any] = None) -> ProcessResult:
        """
        异步处理B站视频推荐（由FeishuAdapter调用）
        支持从缓存数据获取或从Notion重新获取

        Args:
            cached_data: 缓存的视频数据，如果提供则直接使用，否则从Notion获取

        Returns:
            ProcessResult: 处理结果，包含格式化后的视频数据
        """
        # 尝试获取notion服务
        notion_service = self.app_controller.get_service('notion')

        # 判断数据来源：缓存 vs Notion
        if cached_data:
            main_video = cached_data.get("main_video", {})
            additional_videos = cached_data.get("additional_videos", [])
        else:
            # 调用notion服务获取多个B站视频推荐（1+3模式）
            videos_data = notion_service.get_bili_videos_multiple()

            if not videos_data.get("success", False):
                # debug_utils.log_and_print("⚠️ 未获取到有效的B站视频", log_level="WARNING")
                return ProcessResult.error_result("暂时没有找到适合的B站视频，请稍后再试")

            main_video = videos_data.get("main_video", {})
            additional_videos = videos_data.get("additional_videos", [])

            # 处理主视频的已读状态和格式化
            main_video_pageid = main_video.get("pageid", "")
            main_video_is_read = notion_service.is_video_read(main_video_pageid) if main_video_pageid else False
            main_video['is_read'] = main_video_is_read
            main_video['is_read_str'] = " | 已读" if main_video_is_read else ""
            main_video['android_url'] = self.convert_to_bili_app_link(main_video.get('url', ''))

            # 处理附加视频的已读状态和格式化
            for video in additional_videos:
                video_pageid = video.get("pageid", "")
                video_is_read = notion_service.is_video_read(video_pageid) if video_pageid else False
                video['is_read'] = video_is_read
                video['is_read_str'] = " | 已读" if video_is_read else ""

                # 视频标题处理
                title = video.get('title', '无标题视频')
                if len(title) > 30:
                    title = title[:30] + "..."
                video['title'] = title

                video['android_url'] = self.convert_to_bili_app_link(video.get('url', ''))

        # 返回格式化后的数据结构，供feishu_adapter处理
        video_data = {
            'main_video': main_video,
            'additional_videos': additional_videos
        }

        return ProcessResult.success_result("bili_video_data", video_data)

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

    @require_service('notion', "标记服务暂时不可用")
    @safe_execute("标记B站视频为已读失败")
    def handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理标记B站视频为已读（新架构：使用缓存数据避免重新获取）

        Args:
            context: 消息上下文
            action_value: 按钮值，包含pageid、video_index和action_info

        Returns:
            ProcessResult: 包含更新后卡片数据的处理结果
        """
        # 1. 校验依赖服务
        notion_service = self.app_controller.get_service('notion')

        # 2. 先获取video_index，驱动后续参数
        video_index = action_value.get("video_index", "0")
        video_index_int = int(video_index)

        cached_video_data = action_value.get("cached_video_data")
        # 3. 根据video_index获取pageid
        if video_index_int == 0:
            pageid = action_value.get("pageid", "")
        else:
            pageid = cached_video_data['additional_videos'][video_index_int - 1]['pageid']

        # 4. 标记为已读
        if not notion_service.mark_video_as_read(pageid):
            return ProcessResult.error_result("标记为已读失败")

        # 5. 优先用缓存数据更新卡片
        if cached_video_data:
            try:
                if video_index_int == 0:
                    cached_video_data['main_video']['is_read'] = True
                    cached_video_data['main_video']['is_read_str'] = " | 已读"
                else:
                    cached_video_data['additional_videos'][video_index_int - 1]['is_read'] = True
                    cached_video_data['additional_videos'][video_index_int - 1]['is_read_str'] = " | 已读"
            except Exception as e:
                debug_utils.log_and_print(f"⚠️ 更新缓存数据已读状态失败: {e}", log_level="WARNING")

            result = self.process_bili_video_async(cached_video_data)
            if result.success and result.response_type == "bili_video_data":
                video_data = result.response_content
                return ProcessResult.success_result(
                    "bili_card_update",
                    {
                        'main_video': video_data['main_video'],
                        'additional_videos': video_data['additional_videos']
                    }
                )
            else:
                debug_utils.log_and_print("⚠️ 缓存数据处理失败，尝试重新获取", log_level="WARNING")

        # 6. 缓存不可用或处理失败，重新获取
        debug_utils.log_and_print("🔄 重新获取B站视频数据", log_level="INFO")
        result = self.process_bili_video_async()
        if result.success and result.response_type == "bili_video_data":
            video_data = result.response_content
            return ProcessResult.success_result(
                "bili_card_update",
                {
                    'main_video': video_data['main_video'],
                    'additional_videos': video_data['additional_videos']
                }
            )
        return ProcessResult.error_result("获取更新数据失败")

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
            }, parent_id=context.message_id)