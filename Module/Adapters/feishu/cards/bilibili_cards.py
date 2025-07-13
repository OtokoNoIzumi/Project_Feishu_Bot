"""
B站相关卡片管理器

处理B站视频相关的飞书卡片发送、更新和回调
"""

from typing import Dict, Any
from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from Module.Services.constants import CardOperationTypes
from Module.Business.processors import ProcessResult, MessageContext_Refactor, RouteResult
from Module.Services.service_decorators import require_service
from Module.Services.constants import ServiceNames, Messages
from Module.Common.scripts.common import debug_utils


class BilibiliCardManager(BaseCardManager):
    """B站视频卡片管理器"""

    @card_build_safe("B站视频菜单卡片构建失败")
    def build_card(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建B站视频菜单卡片内容"""
        template_params = self._format_bili_video_params(video_data)
        return self._build_template_content(template_params)

    def handle_generate_new_card(self, route_result: RouteResult, context: MessageContext_Refactor, **kwargs) -> None:
        """
        处理生成新卡片动作，先兼容一下route_result，毕竟这是没参数的函数。
        route_result的metadata应该就是必要的参数。
        """
        # 调用外部业务
        video_data = self.message_router.bili.process_bili_video_async()
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
            'message_before_action': '',
            'pageid': main_video.get('pageid', ''),
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

    @require_service('notion', "标记服务暂时不可用")
    def handle_mark_bili_read(self, context: MessageContext_Refactor) -> ProcessResult:
        """
        处理标记B站视频为已读（新架构：使用缓存数据避免重新获取）

        Args:
            context: 消息上下文
            action_value: 按钮值，包含pageid、video_index和action_info

        Returns:
            ProcessResult: 包含更新后卡片数据的处理结果
        """
        # 1. 校验依赖服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)
        action_value = context.content.value
        cached_video_data = action_value.get('cached_video_data', {})
        video_index = action_value.get("video_index", "0")

        # 2. 先获取video_index，驱动后续参数
        video_index_int = int(video_index)

        # 3. 根据video_index获取pageid
        if video_index_int == 0:
            pageid = action_value.get("pageid", "")
        else:
            pageid = cached_video_data['additional_videos'][video_index_int - 1]['pageid']

        # 4. 标记为已读
        if not notion_service.mark_video_as_read(pageid):
            self.sender.send_feishu_message_reply(context, '标记为已读失败')
            return

        # 5. 用缓存数据更新卡片
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
                return

            return self._handle_card_operation_common(
                card_content=self.build_card(cached_video_data),
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type='success',
                toast_message=Messages.VIDEO_MARKED_READ
            )
