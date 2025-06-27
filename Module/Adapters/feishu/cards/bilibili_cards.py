"""
B站相关卡片管理器

处理B站视频相关的飞书卡片发送、更新和回调
"""

from typing import Dict, Any
from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
from Module.Services.constants import CardOperationTypes
from Module.Business.processors import ProcessResult, MessageContext_Refactor


class BilibiliCardManager(BaseCardManager):
    """B站视频卡片管理器"""

    @card_build_safe("B站视频菜单卡片构建失败")
    def build_card(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建B站视频菜单卡片内容"""
        template_params = self._format_bili_video_params(video_data)
        return self._build_template_content(template_params)

    def handle_send_video_card(
        self, result: ProcessResult, context: MessageContext_Refactor
    ) -> P2CardActionTriggerResponse:
        """
        处理发送B站视频卡片动作 - 向后兼容新架构
        """
        video_data = result.response_content
        return self._handle_card_operation_common(
            card_content=self.build_card(video_data),
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type='success',
            user_id=context.user_id
        )

    @card_build_safe("格式化B站视频参数失败")
    def _format_bili_video_params(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """将原始B站数据格式化为模板参数"""
        main_video = video_data.get('main_video', {})
        additional_videos = video_data.get('additional_videos', [])

        # 准备缓存数据（用于回调时传递）
        cached_video_data = {
            'main_video': main_video,
            'additional_videos': additional_videos
        }

        cached_video_data = {
            'card_config_key': self.card_config_key,  # ✅ MessageProcessor路由需要
            'card_action': 'mark_bili_read',
            'pageid': main_video.get('pageid', ''),
            'card_type': 'menu',
            'cached_video_data': cached_video_data
        }
        main_video_cached_data = cached_video_data.copy()
        main_video_cached_data['video_index'] = 0

        # 格式化主视频
        template_params = {
            "main_title": main_video.get('title', ''),
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
            "action_info": main_video_cached_data,
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
                "action_info": additional_videos_cached_data
            }
            template_params["addtional_videos"].append(video_item)

        return template_params
