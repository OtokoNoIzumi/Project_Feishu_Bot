"""
每日信息汇总业务

处理每日信息汇总的完整业务逻辑，包括：
1. B站信息分析数据构建
2. 运营数据获取与处理
3. 日报卡片生成
4. 用户权限验证
"""

from typing import Dict, Any, List
from datetime import datetime
import random

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames, ResponseTypes
from Module.Business.processors.base_processor import (
    BaseProcessor,
    ProcessResult,
    require_service,
    safe_execute,
)
from Module.Services.bili_adskip_service import convert_to_bili_app_link
from Module.Business.shared_process import hex_to_rgb


class DailySummaryBusiness(BaseProcessor):
    """
    每日信息汇总业务

    负责处理每日信息汇总的完整业务流程
    """

    # region 后端业务入口
    # 业务堆栈
    ## 注册
    # main.setup_scheduled_tasks  # 如果后续要区分user，在这里就要把user_id和各自的时间设置进去。虽然现在的user_id都来自飞书，但应该可以直接扩展到其他
    # -> scheduler_service.TaskUtils.get_task_function
    # -> scheduler_service.add_daily_task

    ## 触发
    # 这里service和processor的架构是旧版，以后重构
    # ScheduledEvent的结构不够好，目前type有一份冗余，现在使用的是data里的scheduler_type
    # scheduler_service.trigger_daily_schedule_reminder
    # -> main.handle_scheduled_event
    # -> schedule_processor.create_task
    # -> schedule_processor.daily_summary
    # -> daily_summary_business.create_daily_summary
    @require_service("bili_adskip", "B站广告跳过服务不可用")
    @safe_execute("创建每日信息汇总失败")
    def create_daily_summary(
        self, event_data: Dict[str, Any], main_color: Dict[str, Any], image_key: str
    ) -> ProcessResult:
        """
        创建每日信息汇总消息（主业务入口）

        Args:
            user_id: 用户ID
            services_status: 服务状态信息

        Returns:
            ProcessResult: 处理结果
        """
        # 构建B站信息cache分析数据（整合原来的分散逻辑）
        services_status = event_data.get("services_status")
        analysis_data = self.build_bilibili_analysis_data()

        # 获取运营数据（通过B站广告跳过服务）
        bili_service = self.app_controller.get_service(ServiceNames.BILI_ADSKIP)
        operation_data = bili_service.get_operation_data()
        if operation_data:
            analysis_data["operation_data"] = operation_data

        # 将服务状态信息加入分析数据
        if services_status:
            analysis_data["services_status"] = services_status

        card_content = self.create_daily_summary_card(
            analysis_data, main_color, image_key
        )

        return ProcessResult.user_list_result("interactive", card_content)
    # endregion

    # ------------------------------ 构建B站分析数据 ------------------------------

    @safe_execute("构建B站分析数据失败")
    def build_bilibili_analysis_data(self) -> Dict[str, Any]:
        """
        构建B站信息分析数据（整合get_bili_videos_statistics逻辑）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频缓存数据
        if self.app_controller:
            notion_service = self.app_controller.get_service(ServiceNames.NOTION)
            if notion_service:
                try:
                    # 刷新缓存，获取最新数据（适合早上汇总场景）
                    notion_service.update_bili_cache()

                    # 直接获取缓存数据，不调用统计方法
                    videos = notion_service.cache_data.get(
                        notion_service.bili_cache_key, []
                    )
                    unread_videos = [v for v in videos if v.get("unread", True)]

                    if unread_videos:
                        # 统计各维度数据（移除时长分布和来源分布）
                        priority_stats = {}

                        for video in unread_videos:
                            # 优先级统计
                            priority = video.get("chinese_priority", "Unknown")
                            if priority not in priority_stats:
                                priority_stats[priority] = {"数量": 0, "总时长分钟": 0}

                            priority_stats[priority]["数量"] += 1

                            # 获取时长（分钟）
                            duration_minutes = video.get("duration", 0)
                            try:
                                total_minutes = (
                                    float(duration_minutes) if duration_minutes else 0
                                )
                                priority_stats[priority]["总时长分钟"] += int(
                                    total_minutes
                                )
                            except (ValueError, TypeError):
                                total_minutes = 0

                        # 按优先级生成原始推荐视频（用于AI分析的fallback）
                        original_recommendations = []

                        # 按优先级分组
                        high_priority = [
                            v
                            for v in unread_videos
                            if v.get("chinese_priority") == "💖高"
                        ]
                        medium_priority = [
                            v
                            for v in unread_videos
                            if v.get("chinese_priority") == "😜中"
                        ]
                        low_priority = [
                            v
                            for v in unread_videos
                            if v.get("chinese_priority") == "👾低"
                        ]

                        # 按优先级依次选择，每个优先级内随机选择
                        temp_selected = []
                        for priority_group in [
                            high_priority,
                            medium_priority,
                            low_priority,
                        ]:
                            if len(temp_selected) >= 3:
                                break

                            # 从当前优先级组中随机选择，直到达到3个或该组用完
                            available = [
                                v for v in priority_group if v not in temp_selected
                            ]
                            while available and len(temp_selected) < 3:
                                selected = random.choice(available)
                                temp_selected.append(selected)
                                available.remove(selected)

                        # 格式化原始推荐视频
                        for video in temp_selected:
                            original_recommendations.append(
                                {
                                    "标题": video.get("title", "无标题视频"),
                                    "链接": video.get("url", ""),
                                    "页面ID": video.get("pageid", ""),
                                    "时长": video.get("duration_str", ""),
                                    "优先级": video.get("chinese_priority", ""),
                                    "来源": video.get("chinese_source", ""),
                                }
                            )

                        # 生成AI分析结果（一次调用完成汇总和话题匹配）
                        ai_analysis = self._generate_ai_analysis(unread_videos)

                        # 基于AI话题匹配结果重新构建推荐视频
                        final_recommendations = self._rebuild_recommendations_with_ai(
                            unread_videos, original_recommendations, ai_analysis
                        )

                        total_count = len(unread_videos)
                        return {
                            "date": now.strftime("%Y年%m月%d日"),
                            "weekday": [
                                "周一",
                                "周二",
                                "周三",
                                "周四",
                                "周五",
                                "周六",
                                "周日",
                            ][now.weekday()],
                            "statistics": {
                                "total_count": total_count,
                                "priority_stats": priority_stats,
                                "top_recommendations": final_recommendations,
                                "ai_summary": ai_analysis.get("summary", ""),
                                "ai_quality_score": ai_analysis.get("quality_score", 0),
                            },
                            "source": "notion_statistics",
                            "timestamp": now.isoformat(),
                        }

                except Exception as e:
                    debug_utils.log_and_print(
                        f"获取notion B站统计数据失败: {e}", log_level="WARNING"
                    )

        # 基础状态信息作为fallback
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
                now.weekday()
            ],
            "status": "目前没有待看的B站视频",
            "source": "placeholder",
            "timestamp": now.isoformat(),
        }

    # ------------------------------ 生成AI分析 ------------------------------

    # 类级别常量 - 避免重复定义
    AI_ANALYSIS_BASE_INSTRUCTION = """你是一个专业的内容分析助理。

**核心要求：**
1. 优先汇报高价值内容：新技术突破、行业洞察、实用方法论
2. 整合相似主题，避免重复信息
3. 如果内容质量普遍一般，直接说"今日无特别重点"
4. 控制在80字内，重质量不重数量
5. **必须给出整体内容质量评分(0-10)**

**判断标准：**
- 优先级"高"且内容新颖 → 必须汇报
- 多个UP主谈论同一热点 → 整合汇报
- 纯娱乐、重复话题 → 可忽略
- 实用工具、技术教程 → 重点关注

**质量评分标准：**
- 9-10分：有重大技术突破或深度洞察
- 7-8分：有实用价值或新颖观点
- 4-6分：普通内容，价值一般
- 0-3分：纯娱乐或重复内容"""

    def _build_system_instruction(self, focus_topics: List[str]) -> str:
        """构建系统提示词"""
        task_section = (
            """
**任务：**
1. 分析今日视频清单，**智能判断真正有价值的重点**，而非简单罗列。
2. 分析哪些视频与提供的关注话题相关，给出视频序号和关联度评分(0-10)

**任务1输出格式：**
如有重点：简洁说明几个关键内容点
如无重点：直接说"今日待看内容以[主要类型]为主，无特别重点"

**任务2话题匹配要求：**
- 只返回与关注话题高度相关的视频
- 关联度评分要准确(0-10，10表示最相关)
- 没有相关的可以返回空数组"""
            if focus_topics
            else """
**任务：**
分析今日视频清单，**智能判断真正有价值的重点**，而非简单罗列。

**输出格式：**
如有重点：简洁说明几个关键内容点
如无重点：直接说"今日待看内容以[主要类型]为主，无特别重点" """
        )

        return self.AI_ANALYSIS_BASE_INSTRUCTION + task_section

    def _build_response_schema(self, has_focus_topics: bool) -> Dict[str, Any]:
        """构建响应schema，根据业务需求返回不同结构"""
        # 公共属性定义
        base_properties = {
            "summary": {"type": "string", "description": "今日内容汇总说明"},
            "quality_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": "整体内容质量评分(0-10)",
            },
        }

        base_required = ["summary", "quality_score"]

        if has_focus_topics:
            # 有关注话题时，需要返回匹配结果
            base_properties["topic_matches"] = {
                "type": "array",
                "description": "与关注话题匹配的视频",
                "items": {
                    "type": "object",
                    "properties": {
                        "video_id": {
                            "type": "integer",
                            "description": "视频序号(从1开始)",
                        },
                        "relevance_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 10,
                            "description": "话题关联度评分(0-10)",
                        },
                    },
                    "required": ["video_id", "relevance_score"],
                },
            }
            base_required.append("topic_matches")

        return {
            "type": "object",
            "properties": base_properties,
            "required": base_required,
        }

    def _format_video_list(self, all_videos: List[Dict]) -> List[str]:
        """格式化视频列表"""
        return [
            f"{i}. 《{video.get('title', '无标题')}》 | UP主: {video.get('author', '未知')} | "
            f"优先级: {video.get('chinese_priority', '未知')} | 推荐理由: {video.get('summary', '无理由')}"
            for i, video in enumerate(all_videos, 1)
        ]

    @safe_execute("生成AI分析失败")
    def _generate_ai_analysis(self, all_videos: List[Dict]) -> Dict[str, Any]:
        """使用AI一次性完成内容汇总和话题匹配分析"""
        # 获取服务和配置
        llm_service = self.app_controller.get_service(ServiceNames.LLM)
        if not llm_service or not llm_service.is_available():
            return {
                "summary": "AI服务暂时不可用，无法生成分析",
                "quality_score": 0,
                "topic_matches": [],
            }

        config_service = self.app_controller.get_service(ServiceNames.CONFIG)
        focus_topics = (
            config_service.get("daily_summary", {}).get("focus_topics", [])
            if config_service
            else []
        )

        # 构建提示词和数据
        video_list = self._format_video_list(all_videos)
        topics_text = f"关注话题：{', '.join(focus_topics)}" if focus_topics else ""
        prompt = f"{topics_text}\n\n今日待看视频清单({len(all_videos)}个)：\n{chr(10).join(video_list)}\n\n请按要求分析并返回结果。"

        # 调用LLM
        result = llm_service.structured_call(
            prompt=prompt,
            response_schema=self._build_response_schema(bool(focus_topics)),
            system_instruction=self._build_system_instruction(focus_topics),
            temperature=0.5,
        )

        # 处理结果
        if "error" in result:
            return {
                "summary": f"AI分析失败: {result['error']}",
                "quality_score": 0,
                "topic_matches": [],
            }

        return {
            "summary": result.get("summary", ""),
            "quality_score": result.get("quality_score", 0),
            "topic_matches": result.get("topic_matches", []),
        }

    @safe_execute("重构推荐视频失败")
    def _rebuild_recommendations_with_ai(
        self,
        all_videos: List[Dict],
        original_recommendations: List[Dict],
        ai_analysis: Dict[str, Any],
    ) -> List[Dict]:
        """
        基于AI话题匹配结果重新构建推荐视频列表

        Args:
            all_videos: 所有未读视频
            original_recommendations: 原始推荐视频
            ai_analysis: AI分析结果

        Returns:
            List[Dict]: 重新构建的推荐视频列表
        """
        # 获取AI匹配的高关联度视频
        topic_matches = ai_analysis.get("topic_matches", [])
        high_relevance_videos = []

        for match in topic_matches:
            video_id = match.get("video_id", 0)
            relevance_score = match.get("relevance_score", 0)

            # 只要关联度>=7的视频
            if relevance_score >= 7 and 1 <= video_id <= len(all_videos):
                video_index = video_id - 1  # 转换为0基索引
                video = all_videos[video_index]
                high_relevance_videos.append(
                    {
                        "标题": video.get("title", "无标题视频"),
                        "链接": video.get("url", ""),
                        "页面ID": video.get("pageid", ""),
                        "时长": video.get("duration_str", ""),
                        "优先级": video.get("chinese_priority", ""),
                        "来源": video.get("chinese_source", ""),
                    }
                )

                # 最多3个
                if len(high_relevance_videos) >= 3:
                    break

        # 如果AI推荐的不够3个，用原有逻辑补充
        if len(high_relevance_videos) < 3:
            # 获取AI推荐中已选视频的pageid，避免重复
            selected_pageids = {v.get("页面ID") for v in high_relevance_videos}

            # 从原始推荐中补充
            for video in original_recommendations:
                if video.get("页面ID") not in selected_pageids:
                    high_relevance_videos.append(video)
                    if len(high_relevance_videos) >= 3:
                        break

        return high_relevance_videos

    @safe_execute("创建日报卡片失败")
    def create_daily_summary_card(
        self, analysis_data: Dict[str, Any], main_color: Dict[str, Any], image_key: str
    ) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        source = analysis_data.get("source", "unknown")

        if source == "notion_statistics":
            # notion服务提供的B站分析数据
            content = self.format_notion_bili_analysis(analysis_data)
        else:
            # 占位信息
            content = f"📊 **{analysis_data['date']} {analysis_data['weekday']}** \n\n🔄 **系统状态**\n\n{analysis_data.get('status', '服务准备中...')}"

        # 添加运营数据信息
        operation_data = analysis_data.get("operation_data")
        if operation_data:
            content += self.format_operation_data(operation_data)

        # 添加服务状态信息
        services_status = analysis_data.get("services_status")
        if services_status:
            content += self.format_services_status(services_status)

        card = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "body": {
                "elements": [
                    {"tag": "div", "text": {"content": content, "tag": "lark_md"}},
                    {"tag": "hr"},
                ],
            },
            "header": {
                "template": "blue",
                "title": {"content": "📊 每日信息汇总", "tag": "plain_text"},
            },
        }

        main_color_name = main_color.get("name", "独特的颜色")
        if main_color_name == "独特的颜色":
            main_color_rgb = hex_to_rgb(main_color.get("hex"))
            rgba_str = (
                f"rgba({main_color_rgb[0]},{main_color_rgb[1]},{main_color_rgb[2]}"
            )
            card["config"]["style"] = {
                "color": {
                    "unique": {
                        "light_mode": f"{rgba_str},0.52)",
                        "dark_mode": f"{rgba_str},0.35)",
                    }
                }
            }
            card["header"]["template"] = main_color.get("closest_to", "blue")
        else:
            card["header"]["template"] = main_color_name

        # 如果有推荐视频，添加推荐链接部分
        if source == "notion_statistics":
            statistics = analysis_data.get("statistics", {})

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
                card["body"]["elements"].extend(
                    [
                        {
                            "tag": "div",
                            "text": {
                                "content": "🎬 **今日精选推荐**",
                                "tag": "lark_md",
                            },
                        }
                    ]
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

                    # 视频标题（兼容新旧字段）
                    title = video.get("标题", video.get("title", "无标题视频"))
                    if len(title) > 30:
                        title = title[:30] + "..."

                    # 兼容新旧字段格式
                    priority = video.get(
                        "优先级", video.get("chinese_priority", "未知")
                    )
                    duration = video.get("时长", video.get("duration_str", "未知"))

                    card["body"]["elements"].append(
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}",
                            },
                            "element_id": f"bili_video_{i}",
                        }
                    )

                    # 视频基本信息和链接按钮
                    video_url = video.get("链接", video.get("url", ""))
                    card["body"]["elements"].append(
                        {
                            "tag": "column_set",
                            "layout": "flow",  # 使用flow布局让按钮在一行显示
                            "columns": [
                                {
                                    "tag": "column",
                                    "width": "auto",
                                    "elements": [
                                        {
                                            "tag": "button",
                                            "text": {
                                                "tag": "plain_text",
                                                "content": "📺 B站",
                                            },
                                            "type": "default",
                                            "size": "tiny",
                                            "behaviors": [
                                                {
                                                    "type": "open_url",
                                                    "default_url": video_url,
                                                    "pc_url": video_url,
                                                    "ios_url": video_url,
                                                    "android_url": convert_to_bili_app_link(
                                                        video_url
                                                    ),
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                            + (
                                []
                                if video_read
                                else (
                                    [
                                        {
                                            "tag": "column",
                                            "width": "auto",
                                            "elements": [
                                                {
                                                    "tag": "button",
                                                    "text": {
                                                        "tag": "plain_text",
                                                        "content": "✅ 已读",
                                                    },
                                                    "type": "primary",
                                                    "size": "tiny",
                                                    "value": {
                                                        "card_action": "mark_bili_read_in_daily_summary",
                                                        "pageid": video_pageid,
                                                        "video_index": i,  # 推荐视频序号 (1,2,3)
                                                    },
                                                    "element_id": f"mark_bili_read_{i}",
                                                }
                                            ],
                                        }
                                    ]
                                    if video_pageid
                                    else []
                                )
                            ),
                        }
                    )
        if image_key:
            card["body"]["elements"].append(
                {
                    "tag": "img",
                    "img_key": image_key,
                    "element_id": "daily_summary_image",
                    "title": {"tag": "plain_text", "content": "昨日个性印章"},
                    "alt": {
                        "tag": "plain_text",
                        "content": f"昨天你的{main_color.get('max_weight_category', '')}印章",
                    },
                    "corner_radius": "5px",
                    "scale_type": "crop_center",
                    "size": "80px 90px",
                }
            )

        return card

    @require_service("notion", "标记服务暂时不可用")
    @safe_execute("处理B站标记已读失败")
    def mark_bili_read_v2(self, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理定时卡片中的标记B站视频为已读
        """
        # 获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

        # 获取参数
        pageid = action_value.get("pageid", "")
        video_index = action_value.get("video_index", 1)

        # 执行标记为已读操作
        success = notion_service.mark_video_as_read(pageid)
        if not success:
            return ProcessResult.error_result("标记为已读失败")

        # 定时卡片：基于原始数据重构，只更新已读状态，不重新获取统计数据
        # 这里要用异步的方法来解决了，而且最理想的情况还是不再这里处理，把需求传递出去。
        # 这一步的需求是弹出气泡信息，并且去掉特定element_id的元素。
        return ProcessResult.success_result(
            ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON,
            {
                "toast": {
                    "type": "success",
                    "content": f"已标记第{video_index}个推荐为已读",
                },
                "remove_element_id": f"mark_bili_read_{video_index}",
                "text_element_id": f"bili_video_{video_index}",
            },
        )

    def format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站统计数据"""
        content = f"📊 **{data['date']} {data['weekday']}**"
        content += "\n\n🎯 **B站信息分析汇总**"

        statistics = data.get("statistics", {})

        # 总体统计
        total_count = statistics.get("total_count", None)
        # 兼容新版字段
        if total_count is None:
            total_count = statistics.get("总未读数", 0)
        content += f"\n\n📈 **总计:** {total_count} 个未读视频"

        if total_count > 0:
            # 优先级统计（增加时长总计）
            priority_stats = statistics.get("priority_stats", None)
            if priority_stats is None:
                priority_stats = statistics.get("优先级统计", {})
            if priority_stats:
                content += "\n\n🎯 **优先级分布:**"
                for priority, info in priority_stats.items():
                    # 新版格式：{'😜中': {'数量': 1, '总时长分钟': 51}}
                    count = info.get("数量", info.get("count", 0))
                    total_minutes = info.get("总时长分钟", info.get("total_minutes", 0))
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_str = (
                        f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    )
                    content += f"\n• {priority}: {count} 个 ({time_str})"

            # AI汇总（只显示质量评分>=5的）
            ai_summary = statistics.get("ai_summary", "")
            ai_quality_score = statistics.get("ai_quality_score", 0)
            if ai_summary and ai_quality_score >= 5:
                content += f"\n\n🌟 **AI汇总:**\n{ai_summary}"

        return content

    # ------------------------------ 格式化运营数据 ------------------------------

    def format_operation_data(self, operation_data: Dict[str, Any]) -> str:
        """格式化运营数据信息"""
        content = "\n\n📈 **运营日报**"

        # 获取每日数据
        daily = operation_data.get("daily")
        is_monday = operation_data.get("is_monday", False)

        if daily and daily.get("success", False):
            current = daily.get("current", {})
            comparison = daily.get("comparison", {})

            # 基础统计信息
            date_str = current.get("stats_date", "未知日期")
            content += f"\n📅 **{date_str} 数据概览**"

            # 用户活跃度
            active_users = current.get("active_users", 0)
            new_users = current.get("new_users", 0)
            content += (
                f"\n👥 **用户活跃度:** {active_users} 活跃用户 (+{new_users} 新增)"
            )

            # 内容统计
            new_videos_user = current.get("new_videos_user", 0)
            new_videos_admin = current.get("new_videos_admin", 0)
            total_requests = current.get("total_user_requests", 0)
            content += f"\n🎬 **内容统计:** {new_videos_user} 用户视频 | {new_videos_admin} 管理员视频"
            content += f"\n🔄 **请求总数:** {total_requests} 次"

            # 缓存效率
            cache_hits = current.get("cache_hits", 0)
            cache_rate = current.get("cache_utilization_rate", 0)
            content += f"\n⚡ **缓存效率:** {cache_hits} 次命中 ({cache_rate:.1%})"

            # 拒绝统计
            total_rejections = current.get("total_rejections", 0)
            rejected_users = current.get("rejected_users", 0)
            if rejected_users > 0:
                rejected_rate = total_rejections / rejected_users
                content += f"\n🚫 **拒绝请求:** {total_rejections} 次 ({rejected_users} 用户，人均 {rejected_rate:.1f} 次)"
            else:
                content += (
                    f"\n🚫 **拒绝请求:** {total_rejections} 次 ({rejected_users} 用户)"
                )

            # 显示关键变化趋势
            if comparison:
                trends = []

                # 检查用户活跃度变化
                if "active_users" in comparison:
                    change = comparison["active_users"].get("change", 0)
                    trend = comparison["active_users"].get("trend", "")
                    if abs(change) >= 5:  # 显著变化
                        trend_emoji = "📈" if trend == "up" else "📉"
                        trends.append(f"活跃用户{trend_emoji}{abs(change)}")

                # 检查请求量变化
                if "total_user_requests" in comparison:
                    change = comparison["total_user_requests"].get("change", 0)
                    trend = comparison["total_user_requests"].get("trend", "")
                    if abs(change) >= 20:  # 显著变化
                        trend_emoji = "📈" if trend == "up" else "📉"
                        trends.append(f"请求量{trend_emoji}{abs(change)}")

                if trends:
                    content += f"\n📊 **今日变化:** {' | '.join(trends)}"

            # 广告检测统计（如果有）
            ads_detected = current.get("ads_detected", 0)
            total_ad_duration = current.get("total_ad_duration", 0)
            ad_rate = ads_detected / total_requests if total_requests > 0 else 0
            if ads_detected > 0:
                ad_minutes = int(total_ad_duration / 60) if total_ad_duration else 0
                content += f"\n🎯 **广告检测:** {ads_detected} 个广告，总时长 {ad_minutes} 分钟，占比 {ad_rate:.1%}"

        # 如果是周一，添加周报数据
        if is_monday:
            weekly = operation_data.get("weekly")
            if weekly and weekly.get("success", False):
                content += self.format_weekly_operation_data(weekly.get("data", {}))

        return content

    def format_weekly_operation_data(self, weekly_data: Dict[str, Any]) -> str:
        """格式化周运营数据"""
        content = "\n\n📅 **本周运营概览**"

        # 周期信息
        week_start = weekly_data.get("week_start_date", "")
        week_end = weekly_data.get("week_end_date", "")
        if week_start and week_end:
            content += f"\n🗓️ **统计周期:** {week_start} 至 {week_end}"

        # 用户统计
        total_users = weekly_data.get("total_users", 0)
        weekly_new_users = weekly_data.get("weekly_new_users", 0)
        weekly_churned_users = weekly_data.get("weekly_churned_users", 0)
        active_users = weekly_data.get("active_users", 0)
        content += f"\n👥 **用户概况:** {total_users} 总用户 | {active_users} 活跃 | +{weekly_new_users} 新增 | -{weekly_churned_users} 流失"

        # 付费用户
        free_users = weekly_data.get("free_users", 0)
        paid_users = weekly_data.get("paid_users", 0)
        if paid_users > 0:
            paid_rate = (
                paid_users / (free_users + paid_users) * 100
                if (free_users + paid_users) > 0
                else 0
            )
            content += f"\n💰 **付费情况:** {paid_users} 付费用户 ({paid_rate:.1f}%)"

        # 内容分析
        weekly_unique_videos = weekly_data.get("weekly_unique_videos", 0)
        weekly_requests = weekly_data.get("weekly_total_requests", 0)
        cache_rate = weekly_data.get("weekly_cache_utilization_rate", 0)
        content += f"\n📊 **内容活动:** {weekly_unique_videos} 视频 | {weekly_requests} 请求 | 缓存命中率 {cache_rate:.1%}"

        # 广告分析
        weekly_ad_videos = weekly_data.get("weekly_ad_videos", 0)
        weekly_ad_time_ratio = weekly_data.get("weekly_ad_time_ratio", 0)
        if weekly_ad_videos > 0:
            content += f"\n🎯 **广告分析:** {weekly_ad_videos} 个广告视频 ({weekly_ad_time_ratio:.2%} 时长占比)"

        return content

    # ------------------------------ 格式化服务状态 ------------------------------

    def format_services_status(self, services_status: Dict[str, Any]) -> str:
        """格式化服务状态信息"""
        content = "\n\n🔧 **外部服务状态检测**"
        check_time = services_status.get("check_time", "未知时间")
        content += f"\n检测时间: {check_time}"

        services = services_status.get("services", {})

        # B站API服务状态
        bili_api = services.get("bilibili_api", {})
        if bili_api.get("enabled", False):
            status = bili_api.get("status", "unknown")
            message = bili_api.get("message", "")
            response_time = bili_api.get("response_time", "")
            url = bili_api.get("url", "")

            status_emoji = {
                "healthy": "✅",
                "warning": "⚠️",
                "error": "❌",
                "disabled": "⏸️",
            }.get(status, "❓")

            content += (
                f"\n\n{status_emoji} **{bili_api.get('service_name', 'B站API服务')}**"
            )
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != "error":
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"
        else:
            content += "\n\n⏸️ **B站API服务**: 未启用"

        # Gradio服务状态
        gradio = services.get("gradio", {})
        if gradio.get("enabled", False):
            status = gradio.get("status", "unknown")
            message = gradio.get("message", "")
            response_time = gradio.get("response_time", "")
            url = gradio.get("url", "")

            status_emoji = {
                "healthy": "✅",
                "warning": "⚠️",
                "error": "❌",
                "disabled": "⏸️",
            }.get(status, "❓")

            content += (
                f"\n\n{status_emoji} **{gradio.get('service_name', 'Gradio图像服务')}**"
            )
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != "error":
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"

            # 显示令牌信息
            token_info = gradio.get("token_info", {})
            if token_info.get("has_token", False):
                token_status = token_info.get("status", "unknown")
                if token_status == "valid":
                    expires_in_hours = token_info.get("expires_in_hours", 0)
                    expires_at = token_info.get("expires_at", "")
                    # 格式化时间为 mm-dd hh:mm
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            # 兼容带时区的ISO格式
                            if "+" in expires_at or "Z" in expires_at:
                                # 去掉时区信息
                                expires_at_clean = expires_at.split("+")[0].replace(
                                    "Z", ""
                                )
                            else:
                                expires_at_clean = expires_at
                            dt = datetime.fromisoformat(expires_at_clean)
                            formatted_expires_at = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            formatted_expires_at = expires_at  # 解析失败则原样输出
                    if expires_in_hours <= 24:  # 24小时内过期显示警告
                        content += f"\n⚠️ 令牌将在 {expires_in_hours}小时 后过期 ({formatted_expires_at})"
                    else:
                        content += f"\n🔑 令牌有效期至: {formatted_expires_at}"
                elif token_status == "expired":
                    expires_at = token_info.get("expires_at", "")
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            if "+" in expires_at or "Z" in expires_at:
                                expires_at_clean = expires_at.split("+")[0].replace(
                                    "Z", ""
                                )
                            else:
                                expires_at_clean = expires_at
                            dt = datetime.fromisoformat(expires_at_clean)
                            formatted_expires_at = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            formatted_expires_at = expires_at
                    content += f"\n❌ 令牌已于{formatted_expires_at}过期，需要更新"
                elif token_status == "parse_error":
                    content += "\n⚠️ 令牌时间解析异常"
                elif token_status == "no_expiry_info":
                    content += "\n🔑 令牌已配置 (无过期信息)"
        else:
            content += "\n\n⏸️ **Gradio图像服务**: 未启用"

        return content
