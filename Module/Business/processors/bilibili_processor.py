"""
B站处理器

处理B站视频推荐、卡片生成、已读标记等功能
"""

from Module.Services.constants import ServiceNames, RouteTypes
from Module.Services.bili_adskip_service import convert_to_bili_app_link
from Module.Common.scripts.common import debug_utils
from .base_processor import (
    BaseProcessor,
    ProcessResult,
    require_service,
    safe_execute,
    RouteResult,
)


class BilibiliProcessor(BaseProcessor):
    """
    B站处理器

    处理B站相关的所有功能
    """

    def video_menu_route_choice(self) -> RouteResult:
        """
        处理B站/视频文本指令路由选择
        业务逻辑：判断缓存是否有效，决定是否提示用户"正在同步数据"，否则直接进入异步处理
        返回路由决策，只提供业务标识，前端知识由适配器层映射
        """
        text = ""
        if self.app_controller:
            notion_service = self.app_controller.get_service("notion")
            if notion_service and notion_service.should_show_sync_message():
                text = "正在从Notion同步最新数据，获取可能需要十秒左右，请稍候..."

        # 只提供业务标识和业务参数，不包含前端知识
        return RouteResult.create_route_result(
            route_type=RouteTypes.BILI_VIDEO_CARD,  # 业务标识
            route_params={},  # 当前业务无参数
            message_before_async=text,
        )

    @require_service("notion", "抱歉，B站视频推荐服务暂时不可用")
    @safe_execute("获取B站视频推荐时出现错误，请稍后再试")
    def process_bili_video_async(self) -> ProcessResult:
        """
        异步处理B站视频推荐
        支持从缓存数据获取或从Notion重新获取

        Args:
            cached_data: 缓存的视频数据，如果提供则直接使用，否则从Notion获取

        Returns:
            ProcessResult: 处理结果，包含格式化后的视频数据
        """
        # 尝试获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

        # 调用notion服务获取多个B站视频推荐（1+3模式）
        videos_data = notion_service.get_bili_videos_multiple()

        if not videos_data.get("success", False):
            debug_utils.log_and_print(
                "暂时没有找到适合的B站视频，请稍后再试", log_level="WARNING"
            )
            return {
                "success": False,
                "error_message": "暂时没有找到适合的B站视频，请稍后再试",
                "main_video": {},
                "additional_videos": [],
            }

        main_video = videos_data.get("main_video", {})
        additional_videos = videos_data.get("additional_videos", [])

        # 处理主视频的已读状态和格式化
        main_video_pageid = main_video.get("pageid", "")
        main_video_is_read = (
            notion_service.is_video_read(main_video_pageid)
            if main_video_pageid
            else False
        )
        main_video["is_read"] = main_video_is_read
        main_video["is_read_str"] = " | 已读" if main_video_is_read else ""
        main_video["android_url"] = convert_to_bili_app_link(main_video.get("url", ""))

        # 处理附加视频的已读状态和格式化
        for video in additional_videos:
            video_pageid = video.get("pageid", "")
            video_is_read = (
                notion_service.is_video_read(video_pageid) if video_pageid else False
            )
            video["is_read"] = video_is_read
            video["is_read_str"] = " | 已读" if video_is_read else ""

            # 视频标题处理
            title = video.get("title", "无标题视频")
            if len(title) > 30:
                title = title[:30] + "..."
            video["title"] = title

            video["android_url"] = convert_to_bili_app_link(video.get("url", ""))

        # 返回格式化后的数据结构，供feishu_adapter处理
        return {
            "success": True,
            "main_video": main_video,
            "additional_videos": additional_videos,
        }
