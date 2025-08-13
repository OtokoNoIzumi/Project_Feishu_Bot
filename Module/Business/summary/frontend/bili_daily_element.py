"""B站卡片构建模块

负责B站相关的前端卡片构建和展示逻辑
"""

from typing import Dict, Any, List, Tuple
from Module.Services.bili_adskip_service import convert_to_bili_app_link
from Module.Adapters.feishu.cards.json_builder import JsonBuilder
from Module.Business.shared_process import format_time_label


class BiliDailyElement:
    """B站每日卡片元素构建器"""

    def __init__(self, app_controller):
        self.app_controller = app_controller

    def build_bili_video_elements(
        self, bili_video_data: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """构建B站视频元素"""
        # 日期的信息要分离到公共组件
        elements = []
        video_list = []
        source = bili_video_data.get("source", "unknown")

        if source == "notion_statistics":
            # notion服务提供的B站分析数据
            content = self.format_notion_bili_analysis(bili_video_data)
        else:
            # 占位信息
            content = (
                f"🔄 **系统状态**\n\n{bili_video_data.get('status', '服务准备中...')}"
            )

        elements.append(JsonBuilder.build_markdown_element(content))

        # 如果有推荐视频，添加推荐链接部分
        if source == "notion_statistics":
            statistics = bili_video_data.get("statistics", {})

            # 兼容新版字段名
            top_recommendations = statistics.get("top_recommendations", None)
            if top_recommendations is None:
                top_recommendations = statistics.get("今日精选推荐", [])

            if top_recommendations:
                # 获取notion服务以检查已读状态
                notion_service = None
                if hasattr(self, "app_controller") and self.app_controller:
                    notion_service = self.app_controller.get_service("notion")

                # 添加推荐视频标题
                video_list.append(
                    JsonBuilder.build_markdown_element("🎬 **今日精选推荐**")
                )

                # 添加每个推荐视频的简化展示
                for i, video in enumerate(top_recommendations, 1):
                    # 检查该视频是否已读（兼容新旧字段）
                    video_pageid = video.get("页面ID", video.get("pageid", ""))
                    video_read = (
                        notion_service.is_video_read(video_pageid)
                        if notion_service and video_pageid
                        else False
                    )

                    # 视频标题
                    title = video.get("标题", "无标题视频")
                    if len(title) > 30:
                        title = title[:30] + "..."

                    # 兼容新旧字段格式
                    priority = video.get("优先级", "未知")
                    duration = video.get("时长", "未知")
                    element_id = f"bili_video_{i}"
                    video_info = JsonBuilder.build_markdown_element(
                        f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}",
                        element_id=element_id,
                    )
                    video_list.append(video_info)

                    # 视频基本信息和链接按钮
                    video_url = video.get("链接", "")

                    video_button = JsonBuilder.build_button_element(
                        text="📺 B站",
                        size="tiny",
                        url_data={
                            "default_url": video_url,
                            "pc_url": video_url,
                            "ios_url": video_url,
                            "android_url": convert_to_bili_app_link(video_url),
                        },
                    )

                    video_read_button = JsonBuilder.build_button_element(
                        text="✅ 已读",
                        size="tiny",
                        action_data={
                            "card_action": "mark_bili_read_in_daily_summary",
                            "pageid": video_pageid,
                            "video_index": i,  # 推荐视频序号 (1,2,3)
                        },
                        element_id=f"mark_bili_read_{i}",
                    )
                    button_list = [video_button]
                    if (not video_read) and video_pageid:
                        button_list.append(video_read_button)

                    button_group = JsonBuilder.build_button_group_element(button_list)
                    video_list.append(button_group)

        return elements, video_list

    def format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站统计数据"""
        content = "🎯 **B站信息分析汇总**"

        statistics = data.get("statistics", {})

        # 总体统计
        total_count = statistics.get("total_count", None)

        content += f"\n\n📈 **总计:** {total_count} 个未读视频"

        if total_count > 0:
            # 优先级统计（增加时长总计）
            priority_stats = statistics.get("priority_stats", {})
            if priority_stats:
                content += "\n🎯 **优先级分布:**"
                for priority, info in priority_stats.items():
                    count = info.get("数量", info.get("count", 0))
                    total_minutes = info.get("总时长分钟", info.get("total_minutes", 0))
                    time_str = format_time_label(total_minutes)
                    content += f"\n• {priority}: {count} 个 ({time_str})"

            # AI汇总（只显示质量评分>=5的）
            ai_summary = statistics.get("ai_summary", "")
            ai_quality_score = statistics.get("ai_quality_score", 0)
            if ai_summary and ai_quality_score >= 5:
                content += f"\n🌟 **AI汇总:**\n{ai_summary}"

        return content
