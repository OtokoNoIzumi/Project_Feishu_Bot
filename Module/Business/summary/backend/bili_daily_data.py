"""
B站日常数据处理模块

负责处理B站相关的数据获取、分析和处理
"""

import random
from typing import Dict, List, Any
from Module.Services.constants import ServiceNames
from Module.Common.scripts.common import debug_utils


class BiliDailyData:
    """B站日常数据处理器"""

    def __init__(self, app_controller):
        self.app_controller = app_controller

    # region 外部调用接口

    def get_notion_bili_data(self, _data_params: Dict[str, Any] = None) -> List[Dict]:
        """获取notion B站视频数据"""
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
                    return unread_videos
                except Exception as e:
                    debug_utils.log_and_print(
                        f"获取notion B站统计数据失败: {e}", log_level="WARNING"
                    )
        return []

    def analyze_bili_video_data(self, unread_videos: List[Dict]) -> Dict[str, Any]:
        """分析B站视频数据"""
        # 统计各维度数据
        total_count = len(unread_videos)
        priority_stats = self._calculate_priority_stats(unread_videos)

        # 按优先级生成原始推荐视频
        original_recommendations = self._generate_original_recommendations(
            unread_videos
        )

        # 生成AI分析结果——这个的依赖关系的先后顺序要再考虑一下，目前llm也是整合在app_controller里的service。
        # 从这个角度来说app_controller要成为各种方法的背景信息，方便直接调用。
        # 这里不支持异步，未来要调整，但先跑通业务吧
        ai_analysis = self._generate_video_ai_analysis(unread_videos)

        # 基于AI话题匹配结果重新构建推荐视频
        final_recommendations = self._rebuild_recommendations_with_ai(
            unread_videos, original_recommendations, ai_analysis
        )

        return {
            "statistics": {
                "total_count": total_count,
                "priority_stats": priority_stats,
                "ai_summary": ai_analysis.get("summary", ""),
                "ai_quality_score": ai_analysis.get("quality_score", 0),
                "top_recommendations": final_recommendations,
            },
            "source": "notion_statistics",
        }

    # endregion

    # region 数据分析

    def _calculate_priority_stats(self, unread_videos: List[Dict]) -> Dict[str, Any]:
        """计算优先级统计"""
        priority_stats = {}

        for video in unread_videos:
            # 优先级统计
            priority = video.get("chinese_priority", "Unknown")
            priority_stats.setdefault(priority, {"数量": 0, "总时长分钟": 0})

            priority_stats[priority]["数量"] += 1

            # 获取时长（分钟）
            duration_minutes = video.get("duration", 0)
            try:
                total_minutes = float(duration_minutes) if duration_minutes else 0
                priority_stats[priority]["总时长分钟"] += int(total_minutes)
            except (ValueError, TypeError):
                total_minutes = 0

        return priority_stats

    def _generate_original_recommendations(
        self, unread_videos: List[Dict]
    ) -> List[Dict]:
        """生成原始推荐视频"""
        original_recommendations = []

        # 按优先级分组
        high_priority = [
            v for v in unread_videos if v.get("chinese_priority") == "💖高"
        ]
        medium_priority = [
            v for v in unread_videos if v.get("chinese_priority") == "😜中"
        ]
        low_priority = [v for v in unread_videos if v.get("chinese_priority") == "👾低"]

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
            available = [v for v in priority_group if v not in temp_selected]
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

        return original_recommendations

    def _generate_video_ai_analysis(self, all_videos: List[Dict]) -> Dict[str, Any]:
        """使用AI一次性完成内容汇总和话题匹配分析"""
        # 获取服务和配置
        llm_service = self.app_controller.get_service(ServiceNames.LLM)
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
            response_schema=self._build_video_response_schema(bool(focus_topics)),
            system_instruction=self._build_video_system_instruction(focus_topics),
            temperature=0.5,
        )

        # 处理结果
        if "error" in result:
            return {
                "summary": f"AI分析失败: {result['error']}",
                "quality_score": 0,
                "topic_matches": [],
            }

        return result

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

    def _format_video_list(self, all_videos: List[Dict]) -> List[str]:
        """格式化视频列表"""
        return [
            f"{i}. 《{video.get('title', '无标题')}》 | UP主: {video.get('author', '未知')} | "
            f"优先级: {video.get('chinese_priority', '未知')} | 推荐理由: {video.get('summary', '无理由')}"
            for i, video in enumerate(all_videos, 1)
        ]

    # endregion

    # region AI分析
    AI_VIDEO_ANALYSIS_BASE_INSTRUCTION = """你是一个专业的内容分析助理。

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

    def _build_video_system_instruction(self, focus_topics: List[str]) -> str:
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

        return self.AI_VIDEO_ANALYSIS_BASE_INSTRUCTION + task_section

    def _build_video_response_schema(self, has_focus_topics: bool) -> Dict[str, Any]:
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

    # endregion
