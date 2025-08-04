"""每日信息汇总业务

处理每日信息汇总的完整业务逻辑，包括：
1. B站信息分析数据构建
2. 运营数据获取与处理
3. 日报卡片生成
4. 用户权限验证
"""

import os
from typing import Dict, Any, List
from datetime import datetime, timedelta
import random

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    ResponseTypes,
    SchedulerConstKeys,
    AdapterNames,
    ColorTypes,
)
from Module.Business.processors.base_processor import (
    BaseProcessor,
    ProcessResult,
    require_service,
    safe_execute,
)
from Module.Services.bili_adskip_service import convert_to_bili_app_link
from Module.Business.shared_process import format_time_label
from Module.Business.routine_record import RoutineRecord, wax_stamp_prompt
from Module.Adapters.feishu.cards.json_builder import JsonBuilder


class DailySummaryBusiness(BaseProcessor):
    """
    每日信息汇总业务

    负责处理每日信息汇总的完整业务流程
    """

    # region 后端业务入口
    # 业务堆栈
    # 注册
    # main.setup_scheduled_tasks  # 如果后续要区分user，在这里就要把user_id和各自的时间设置进去。虽然现在的user_id都来自飞书，但应该可以直接扩展到其他
    # -> scheduler_service.TaskUtils.get_task_function
    # -> scheduler_service.add_daily_task

    # 触发
    # 这里service和processor的架构是旧版，以后重构
    # ScheduledEvent的结构不够好，目前type有一份冗余，现在使用的是data里的scheduler_type
    # scheduler_service.trigger_daily_schedule_reminder
    # -> main.handle_scheduled_event
    # -> schedule_processor.create_task
    # -> schedule_processor.daily_summary 这里更多应该是定时属性，业务集中在下面
    # -> daily_summary_business.create_daily_summary
    # -> main.handle_scheduled_event

    @require_service("bili_adskip", "B站广告跳过服务不可用")
    @safe_execute("创建每日信息汇总失败")
    def create_daily_summary(self, event_data: Dict[str, Any]) -> ProcessResult:
        """
        创建每日信息汇总消息（主业务入口）

        Args:
            user_id: 用户ID
            services_status: 服务状态信息

        Returns:
            ProcessResult: 处理结果
        """
        # 构建B站信息cache分析数据（整合原来的分散逻辑）
        # analysis 是后端的数据处理逻辑，然后提供给前端的卡片进行build_card
        user_id = event_data.get(SchedulerConstKeys.ADMIN_ID)
        daily_raw_data = self.get_daily_raw_data(user_id)

        card_content = self.create_daily_summary_card(daily_raw_data)

        return ProcessResult.user_list_result("interactive", card_content)

    # endregion

    # region 采集模块数据
    # 假设user_id信息存在来做，但实际上都先赋值为我——管理员id
    # 业务信息顺序应该是从一个配置获得某个user_id的daily_summary 的触发时间，然后到时间了开始进入本模块采集信息，再通过前端发出去
    # 这里是一个包含采集和处理两个部分的总接口
    GRANULARITY_MINUTES = 30

    def get_daily_raw_data(self, user_id: str) -> Dict[str, Any]:
        """
        获取每日信息汇总原始数据
        """
        # 后续要改成从用户数据读取，这里先写死
        # 要不要进一步分离获取数据和处理，我觉得可以有，要合并回来就是剪切一下的事
        # 全开是我的，如果是其他user_id就只开日常分析
        # AI的分析可能要并行，我感觉两个是完全无关的
        # 不同人用的图片也可能不一样？但应该现在基本不着急，毕竟豆包也没啥开销
        info_modules = {
            "routine": {
                "name": "日常分析",
                "system_permission": True,
                "user_enabled": True,
                "data_method": "get_routine_data",
                "image_method": "generate_routine_image",
            },
            "bili_video": {
                "name": "B站视频",
                "system_permission": True,
                "user_enabled": True,
                "sync_read_mark": True,  # 仅本地标记，还是额外同步到notion
                "data_method": "get_notion_bili_data",
                "analyze_method": "analyze_bili_video_data",
            },
            "bili_adskip": {
                "name": "B站广告跳过",
                "system_permission": True,
                "user_enabled": True,
                "data_method": "get_operation_data",
            },
            "services_status": {
                "name": "服务状态",
                "system_permission": True,
                "user_enabled": True,
                "data_method": "get_services_status",
            },
        }

        for module_name, module_info in info_modules.items():
            if module_info["system_permission"] and module_info["user_enabled"]:
                data_method = module_info["data_method"]
                if hasattr(self, data_method):
                    module_data = getattr(self, data_method)(user_id)
                    if module_data:
                        module_info["data"] = module_data
                        analyze_method = module_info.get("analyze_method", "")
                        if hasattr(self, analyze_method):
                            module_info["info"] = getattr(self, analyze_method)(
                                module_data
                            )
                else:
                    debug_utils.log_and_print(
                        f"模块{module_name}没有实现{data_method}方法",
                        log_level="WARNING",
                    )

        info_modules["system_status"] = {
            "name": "系统状态",
            "data": {
                "date": datetime.now().strftime("%Y年%m月%d日"),
                "weekday": [
                    "周一",
                    "周二",
                    "周三",
                    "周四",
                    "周五",
                    "周六",
                    "周日",
                ][datetime.now().weekday()],
            },
        }

        return info_modules

    # endregion

    # region B站视频推荐

    def get_notion_bili_data(self, _user_id: str = None) -> List[Dict]:
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
        return None

    def analyze_bili_video_data(self, unread_videos: List[Dict]) -> Dict[str, Any]:
        """处理B站分析数据"""
        # 后续调整输出内容，比如只关注收藏夹里的时长和总时长/总量——用来监测订阅量是否过多
        # 这已经是模块的1级入口了

        # 统计各维度数据
        total_count = len(unread_videos)
        priority_stats = self._calculate_priority_stats(unread_videos)

        # 按优先级生成原始推荐视频
        original_recommendations = self._generate_original_recommendations(
            unread_videos
        )

        # 生成AI分析结果——这个的依赖关系的先后顺序要再考虑一下，目前llm也是整合在app_controller里的service。
        # 从这个角度来说app_controller要成为各种方法的背景信息，方便直接调用。
        ai_analysis = self._generate_ai_analysis(unread_videos)

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

        return result

    def _format_video_list(self, all_videos: List[Dict]) -> List[str]:
        """格式化视频列表"""
        return [
            f"{i}. 《{video.get('title', '无标题')}》 | UP主: {video.get('author', '未知')} | "
            f"优先级: {video.get('chinese_priority', '未知')} | 推荐理由: {video.get('summary', '无理由')}"
            for i, video in enumerate(all_videos, 1)
        ]

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

    def _build_fallback_analysis_data(self) -> Dict[str, Any]:
        """构建fallback分析数据"""
        now = datetime.now()
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
                now.weekday()
            ],
            "status": "目前没有待看的B站视频",
            "source": "placeholder",
            "timestamp": now.isoformat(),
        }

    # endregion

    # region 日常分析
    def get_routine_data(self, user_id: str = None) -> Dict[str, Any]:
        """获取日常分析数据"""
        # image key这个先做例外，但可以先完成prompt的处理，甚至image_data，反正最后是给到前端。
        # 获取颜色聚合数据，先用我自己的id，以后再拓展
        # 数据的深度按日、周、月、季、年来分，每个都是独立方法，用条件调用，而不是内部监测
        routine_business = RoutineRecord(self.app_controller)

        now = datetime.now()
        is_monday = now.weekday() == 0  # 0是周一
        is_first_day_of_month = now.day == 1
        is_first_day_of_quarter = now.month % 3 == 1 and now.day == 1
        is_first_day_of_year = now.month == 1 and now.day == 1

        # 日：待办事项，提醒事项，image_key，主颜色
        # 周：日 + 周日程分析，周image_key，周的日程记录表，规律分析
        # 月：日 + 周 + 月程分析——最好维度有区别，否则就要因为月把周关闭掉，我不想有多份重复信息

        datetime_zero = datetime(now.year, now.month, now.day)
        start_time = datetime_zero - timedelta(days=now.day - 1)
        end_time = start_time + timedelta(days=1)

        main_color, color_palette = routine_business.calculate_color_palette(
            user_id,
            start_time,
            end_time,
        )
        raw_prompt = wax_stamp_prompt(
            color_palette, subject_name=main_color.get("max_weight_category", "")
        )

        image_service = self.app_controller.get_service(ServiceNames.IMAGE)
        result = image_service.hunyuan_image_generator.generate_image(
            raw_prompt,
            size="3:4",
        )
        image_path = result.get("file_path")
        image_key = self.app_controller.get_adapter(
            AdapterNames.FEISHU
        ).sender.upload_and_get_image_key(image_path)

        # 删除图片
        if image_path:
            os.remove(image_path)

        weekly_data = None
        if is_monday:
            weekly_data = self.get_weekly_data(
                user_id, granularity_minutes=self.GRANULARITY_MINUTES
            )

        routine_data = {
            "daily": {
                "image_key": image_key,
                "main_color": main_color,
                "color_palette": color_palette,
            },
            "weekly": weekly_data,
        }

        return routine_data

    def get_weekly_data(
        self, user_id: str = None, granularity_minutes: int = 120
    ) -> Dict[str, Any]:
        """获取周分析数据"""
        routine_business = RoutineRecord(self.app_controller)
        now = datetime.now()
        end_time = datetime(now.year, now.month, now.day) - timedelta(
            days=now.weekday()
        )
        start_time = end_time - timedelta(days=7)

        records = routine_business.load_event_records(user_id)
        records = records.get("records", {})

        filtered_records = routine_business.preprocess_and_filter_records(
            records, start_time, end_time
        )
        event_map = routine_business.cal_event_map(user_id)

        table_data = self.format_table_data(
            filtered_records,
            start_time,
            event_map,
            granularity_minutes,
            user_id,
        )

        return table_data

    def format_table_data(
        self,
        records: List[Dict[str, Any]],
        start_time: datetime,
        event_map: Dict[str, Any],
        granularity_minutes: int = 120,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """格式化表格数据 - 构建真实的周数据结构"""
        routine_business = RoutineRecord(self.app_controller)

        # 生成时间标签
        match granularity_minutes:
            case 30:
                time_labels = [
                    label
                    for hour in range(24)
                    for label in (f"{hour:02d}:00", f"{hour:02d}:30")
                ]
            case 60:
                time_labels = [f"{hour:02d}:00" for hour in range(24)]
            case _:
                time_labels = [f"{hour:02d}:00" for hour in range(0, 24, 2)]

        # 初始化周数据结构
        week_data = {
            "time_labels": time_labels,
            "days": {
                "mon": {},
                "tue": {},
                "wed": {},
                "thu": {},
                "fri": {},
                "sat": {},
                "sun": {},
            },
        }

        # 为每一天处理数据
        current_day = start_time
        day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        for day_idx in range(7):
            day_key = day_keys[day_idx]
            day_start = current_day
            day_end = day_start + timedelta(days=1)

            # 获取当天的记录
            day_records = []
            for record in records:
                record_start = record.get("start_dt")
                record_end = record.get("end_dt")

                # 判断记录是否与当天有交集
                if record_start < day_end and record_end > day_start:
                    day_records.append(record)

            # 为当天的每个时间槽生成数据
            for time_label in time_labels:
                hour_minute = time_label.split(":")
                slot_hour = int(hour_minute[0])
                slot_minute = int(hour_minute[1])

                slot_start = day_start.replace(
                    hour=slot_hour, minute=slot_minute, second=0, microsecond=0
                )
                slot_end = slot_start + timedelta(minutes=granularity_minutes)

                # 生成该时间槽的原子时间线
                atomic_timeline = routine_business.generate_atomic_timeline(
                    day_records, slot_start, slot_end
                )

                if atomic_timeline:
                    # 计算颜色和标签
                    # 周的模式显示的是event_name，不适合融合颜色，而是匹配颜色

                    # 找到持续时间最长的事件作为主要事件
                    sorted_atomic_timeline = sorted(
                        atomic_timeline,
                        key=lambda x: x["duration_minutes"],
                        reverse=True,
                    )
                    slot_event_label = sorted_atomic_timeline[0]["source_event"][
                        "event_name"
                    ]
                    slot_event_info = event_map.get(slot_event_label, {})
                    slot_event_color = slot_event_info.get(
                        "color", ColorTypes.GREY
                    ).option_value

                    final_color, palette_data = (
                        routine_business.calculate_color_palette(
                            user_id,
                            slot_start,
                            slot_end,
                            event_color_map=event_map,
                            timeline_data=atomic_timeline,
                        )
                    )

                    # slot_color_name = final_color.get("option_value", ColorTypes.GREY.option_value)

                    slot_category_label = final_color.get("max_weight_category", "空闲")

                    week_data["days"][day_key][time_label] = {
                        "text": slot_event_label,
                        "color": slot_event_color,
                        "category_label": slot_category_label,
                    }
                else:
                    # 空时间槽
                    week_data["days"][day_key][time_label] = {
                        "text": "空闲",
                        "color": ColorTypes.GREY.option_value,
                        "category_label": "空闲",
                    }

            current_day += timedelta(days=1)

        return week_data

    # endregion

    # region 其他小模块

    # 切片广告运营
    def get_operation_data(self, _user_id: str = None) -> Dict[str, Any]:
        """获取切片广告运营数据"""
        bili_service = self.app_controller.get_service(ServiceNames.BILI_ADSKIP)
        operation_data = bili_service.get_operation_data()

        return operation_data

    # 服务状态
    def get_services_status(self, _user_id: str = None) -> Dict[str, Any]:
        """获取服务状态"""
        scheduler_service = self.app_controller.get_service(ServiceNames.SCHEDULER)
        services_status = scheduler_service.check_services_status()

        return services_status

    # endregion

    # region 前端日报卡片

    @safe_execute("创建日报卡片失败")
    def create_daily_summary_card(
        self, daily_raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        # 内容是按照顺序排列的，所以天然可以分组，还是用card_registry里的方法。

        main_color = (
            daily_raw_data.get("routine", {}).get("data", {}).get("main_color", {})
        )
        main_color_name = main_color.get("name", "独特的颜色")
        header_template = (
            main_color_name
            if main_color_name != "独特的颜色"
            else main_color.get("closest_to", ColorTypes.BLUE.value)
        )

        header = JsonBuilder.build_card_header(
            title="📊 每日信息汇总",
            template=header_template,
        )
        elements = self.build_daily_summary_elements(daily_raw_data)
        if elements:
            system_status = daily_raw_data.get("system_status", {}).get("data", {})
            date = system_status.get("date", "")
            weekday = system_status.get("weekday", "")
            date_element = JsonBuilder.build_markdown_element(f"**{date} {weekday}**")
            elements.insert(0, date_element)

        return JsonBuilder.build_base_card_structure(elements, header)

    def build_daily_summary_elements(
        self, daily_raw_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建每日信息汇总元素"""
        elements = []

        bili_video_data = daily_raw_data.get("bili_video", {}).get("info", {})
        video_list = []
        if bili_video_data:
            video_info, video_list = self.build_bili_video_elements(bili_video_data)
            elements.extend(video_info)

        operation_data = daily_raw_data.get("bili_adskip", {}).get("data", {})
        if operation_data:
            elements.extend(self.build_operation_elements(operation_data))

        services_status = daily_raw_data.get("services_status", {}).get("data", {})
        if services_status:
            elements.extend(self.build_services_status_elements(services_status))

        elements.append(JsonBuilder.build_line_element())

        elements.extend(video_list)

        routine_data = daily_raw_data.get("routine", {}).get("data", {})
        if routine_data:
            elements.extend(self.build_routine_elements(routine_data))

        return elements

    # region B站信息组件

    def build_bili_video_elements(
        self, bili_video_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
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

    # endregion

    # region 运营数据组件
    def build_operation_elements(
        self, operation_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建运营数据元素"""
        elements = []
        content = self.format_operation_data(operation_data)
        elements.append(JsonBuilder.build_markdown_element(content))
        return elements

    def format_operation_data(
        self, operation_data: Dict[str, Any], detail_mode: bool = False
    ) -> str:
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
            if detail_mode:
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

            if detail_mode:
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

    # endregion

    # region 服务状态组件
    def build_services_status_elements(
        self, services_status: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建服务状态元素"""
        elements = []
        content = self.format_services_status(services_status)
        elements.append(JsonBuilder.build_markdown_element(content))
        return elements

    def format_services_status(self, services_status: Dict[str, Any]) -> str:
        """格式化服务状态信息"""
        content = ""
        # 两个\n开头会被自动处理掉，所以不用额外写代码

        services = services_status.get("services", {})

        # B站API服务状态，只在异常是显示
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

            if status != "healthy":
                content += f"\n\n{status_emoji} **{bili_api.get('service_name', 'B站API服务')}**"
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
            if status != "healthy":
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

    # endregion

    # region 日常组件

    def build_routine_elements(
        self, routine_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建日常元素"""
        elements = []
        image_key = routine_data.get("daily", {}).get("image_key", "")
        main_color = routine_data.get("daily", {}).get("main_color", {})
        weekly_data = routine_data.get("weekly", {})

        if image_key:
            image_element = JsonBuilder.build_image_element(
                image_key=image_key,
                alt=f"昨天你的{main_color.get('max_weight_category', '')}印章",
                title="昨日个性印章",
                corner_radius="5px",
                scale_type="crop_center",
                size="80px 90px",
            )
            elements.append(image_element)

        # 构建表格结构
        if weekly_data:
            elements.append(JsonBuilder.build_markdown_element("上周时间表"))
            columns = []
            columns.append(
                JsonBuilder.build_table_column_element(
                    name="time",
                    display_name="时间",
                    data_type="text",
                    width="80px",
                )
            )
            day_dict = {
                "mon": "周一",
                "tue": "周二",
                "wed": "周三",
                "thu": "周四",
                "fri": "周五",
                "sat": "周六",
                "sun": "周日",
            }
            for day_key, day_name in day_dict.items():
                columns.append(
                    JsonBuilder.build_table_column_element(
                        name=day_key,
                        display_name=day_name,
                        data_type="options",
                        width="120px",
                    )
                )
            table_element = JsonBuilder.build_table_element(
                columns=columns,
                rows=[],
                freeze_first_column=True,
            )

            time_labels = weekly_data.get("time_labels", [])
            days_data = weekly_data.get("days", {})

            DEFAULT_SLOT_DATA = {
                "text": "空闲",
                "color": ColorTypes.GREY.option_value,
                "category_label": "空闲",
            }

            for time_label in time_labels:
                row = {"time": time_label}

                for day_key in day_dict.keys():
                    day_data = days_data.get(day_key, {})
                    slot_data = day_data.get(time_label, DEFAULT_SLOT_DATA)

                    row[day_key] = [
                        {
                            "text": slot_data.get(
                                "text", DEFAULT_SLOT_DATA.get("text")
                            ),
                            "color": slot_data.get(
                                "color", DEFAULT_SLOT_DATA.get("color")
                            ),
                        }
                    ]

                table_element["rows"].append(row)

            elements.append(table_element)
        return elements

    # endregion

    # region 回调处理

    @require_service("notion", "标记服务暂时不可用")
    @safe_execute("处理B站标记已读失败")
    def mark_bili_read_v2(self, action_value: Dict[str, Any]) -> ProcessResult:
        """处理B站视频标记已读的回调"""
        # 获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

        # 获取参数
        pageid = action_value.get("pageid", "")
        video_index = action_value.get("video_index", 1)

        # 执行标记为已读操作
        success = notion_service.mark_video_as_read(pageid)
        if not success:
            return ProcessResult.error_result("标记为已读失败")

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

    # endregion
