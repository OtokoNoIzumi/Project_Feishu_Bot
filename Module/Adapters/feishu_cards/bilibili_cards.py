"""
B站相关卡片管理器

处理B站视频相关的飞书卡片发送、更新和回调
"""

from typing import Dict, Any, Optional, List
from Module.Common.scripts.common import debug_utils
from .base_card_manager import BaseCardManager


class BilibiliCardManager(BaseCardManager):
    """B站卡片管理器"""

    def __init__(self):
        """初始化B站卡片管理器"""
        super().__init__()

    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        return "B站"

    def _initialize_templates(self):
        """初始化B站卡片模板配置"""
        self.templates = {
            "bili_video_menu": {
                "template_id": "AAqBPdq4sxIy5",
                "template_version": "1.0.6"
            }
        }

    # 卡片构建方法组（只负责数据格式化）
    def build_bili_video_menu_card(self, bili_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建B站视频菜单卡片内容"""
        try:
            template_params = self._format_bili_video_params(bili_data)
            content = self._build_template_content("bili_video_menu", template_params)
            return content

        except Exception as e:
            debug_utils.log_and_print(f"❌ B站视频菜单卡片构建失败: {e}", log_level="ERROR")
            raise

    # 参数格式化方法组
    def _format_bili_video_params(self, bili_data: Dict[str, Any]) -> Dict[str, Any]:
        """将原始B站数据格式化为模板参数"""
        try:
            main_video = bili_data.get('main_video', {})
            additional_videos = bili_data.get('additional_videos', [])

            # 准备缓存数据（用于回调时传递）
            cached_video_data = {
                'main_video': main_video,
                'additional_videos': additional_videos
            }

            cached_video_data = {
                'action': 'mark_bili_read',
                'pageid': main_video.get('pageid', ''),
                'card_type': 'menu',
                'cached_video_data': cached_video_data
            }
            main_video_cached_data = cached_video_data.copy()
            main_video_cached_data['video_index'] = 0

            # 格式化主视频
            template_params = {
                "main_title": main_video.get('title', ''),
                "main_pageid": str(main_video.get('pageid', '')),
                "main_priority": str(main_video.get('chinese_priority', '')),
                "main_duration_str": str(main_video.get('duration_str', '')),
                "main_author": str(main_video.get('author', '')),
                "main_source": str(main_video.get('chinese_source', '')),
                "main_upload_date_str": str(main_video.get('upload_date', '')),
                "main_summary": str(main_video.get('summary', '')),
                "main_url": main_video.get('url', ''),
                "main_android_url": main_video.get('android_url', ''),
                "main_is_read_str": main_video.get('is_read_str', ''),
                "main_is_read": main_video.get('is_read', False),
                "action_info": main_video_cached_data,  # 添加缓存数据
                "addtional_videos": []
            }

            # 格式化附加视频列表
            for i, video in enumerate(additional_videos[:4]):  # 限制最多4个附加视频
                additional_videos_cached_data = cached_video_data.copy()
                additional_videos_cached_data['video_index'] = i + 1
                video_item = {
                    "title": video.get('title', ''),
                    "pageid": str(video.get('pageid', '')),
                    "priority": str(video.get('chinese_priority', '')),
                    "duration_str": str(video.get('duration_str', '')),
                    "video_index": str(i + 1),
                    "is_read_str": video.get('is_read_str', ''),
                    "is_read": video.get('is_read', False),
                    "url": video.get('url', ''),
                    "android_url": video.get('android_url', ''),
                    "action_info": additional_videos_cached_data  # 每个按钮都添加缓存数据
                }
                template_params["addtional_videos"].append(video_item)

            return template_params

        except Exception as e:
            debug_utils.log_and_print(f"❌ 格式化B站视频参数失败: {e}", log_level="ERROR")
            raise