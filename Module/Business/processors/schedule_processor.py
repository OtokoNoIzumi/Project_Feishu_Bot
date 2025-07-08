"""
定时任务处理器

处理每日汇总、B站更新等定时任务相关功能
"""

import re
import json
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import SchedulerTaskTypes, ServiceNames, ResponseTypes, SchedulerConstKeys, DefaultValues, EnvVars
from Module.Business.processors.bilibili_processor import convert_to_bili_app_link
from Module.Services.message_aggregation_service import MessagePriority
from Module.Business.daily_summary_business import DailySummaryBusiness

class ScheduleProcessor(BaseProcessor):
    """
    定时任务处理器

    处理各种定时任务相关的功能
    """

    def __init__(self, app_controller=None):
        super().__init__(app_controller)
        self._load_config()

    def _load_config(self):
        """加载配置"""
        # 统一默认值
        self.bili_api_base_url = DefaultValues.DEFAULT_BILI_API_BASE
        self.bili_admin_secret = DefaultValues.DEFAULT_ADMIN_SECRET

        if not self.app_controller:
            return

        config_service = self.app_controller.get_service(ServiceNames.CONFIG)
        if not config_service:
            return

        # 获取B站API配置
        self.bili_api_base_url = config_service.get_env(EnvVars.BILI_API_BASE, self.bili_api_base_url)
        self.bili_admin_secret = config_service.get_env(EnvVars.ADMIN_SECRET_KEY, self.bili_admin_secret)

    @safe_execute("创建定时消息失败")
    def create_task(self, event_data: Dict[str, Any]) -> ProcessResult:
        """
        创建定时消息（统一入口，路由逻辑封装在内部）

        Args:
            scheduler_type: 定时任务类型
            event_data: 事件数据

        Returns:
            ProcessResult: 处理结果
        """

        scheduler_type = event_data.get(SchedulerConstKeys.SCHEDULER_TYPE)
        try:
            match scheduler_type:
                case SchedulerTaskTypes.DAILY_SCHEDULE:
                    services_status = event_data.get('services_status')
                    return self.daily_summary(services_status)
                case SchedulerTaskTypes.BILI_UPDATES:
                    sources = event_data.get('sources')
                    api_result = event_data.get('api_result')
                    return self.bili_notification(sources, api_result)
                case SchedulerTaskTypes.PERSONAL_STATUS_EVAL:
                    status_data = event_data.get('status_data')
                    evaluation_time = event_data.get('evaluation_time')
                    return self.personal_status_evaluation(status_data, evaluation_time)
                case SchedulerTaskTypes.WEEKLY_REVIEW:
                    weekly_data = event_data.get('weekly_data')
                    review_week = event_data.get('review_week')
                    return self.weekly_review(weekly_data, review_week)
                case SchedulerTaskTypes.MONTHLY_REVIEW:
                    monthly_data = event_data.get('monthly_data')
                    review_month = event_data.get('review_month')
                    return self.monthly_review(monthly_data, review_month)
                case _:
                    return ProcessResult.error_result(f"不支持的定时任务类型: {scheduler_type}")
        except Exception as e:
            debug_utils.log_and_print(f"创建定时消息失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"创建定时消息失败: {str(e)}")

    @safe_execute("创建每日信息汇总失败")
    def daily_summary(self, services_status: Dict[str, Any] = None) -> ProcessResult:
        """创建每日信息汇总消息（7:30定时卡片容器）"""
        # 获取有权限的用户列表
        if not self.app_controller:
            return ProcessResult.error_result("应用控制器不可用")

        permission_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        if not permission_service:
            return ProcessResult.error_result("用户权限服务不可用")

        enabled_users = permission_service.get_enabled_users_for_business("daily_summary")
        if not enabled_users:
            debug_utils.log_and_print("没有启用日报功能的用户，跳过定时任务", log_level="INFO")
            return ProcessResult.success_result("no_reply", {"message": "没有启用日报功能的用户"})

        # 创建日报业务实例
        daily_summary_business = DailySummaryBusiness(app_controller=self.app_controller)

        # 调用新的日报业务逻辑
        result = daily_summary_business.create_daily_summary(services_status)
        if result.success:
            result.user_list = enabled_users

        return result

    @safe_execute("创建B站更新提醒失败")
    def bili_notification(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> ProcessResult:
        """创建B站更新提醒消息"""
        # 生成B站更新通知卡片，传入API结果数据
        card_content = self.create_bilibili_updates_card(sources, api_result)

        return ProcessResult.success_result("interactive", card_content)

    def create_bilibili_updates_card(self, sources: Optional[List[str]] = None, api_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建B站更新通知卡片"""
        source_text = "、".join(sources) if sources else "全部源"
        now = datetime.now()

        # 基础卡片结构
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "content": "📺 B站数据处理完成",
                    "tag": "plain_text"
                }
            },
            "elements": []
        }

        # 添加基础信息
        card["elements"].extend([
            {
                "tag": "div",
                "text": {
                    "content": f"🔄 **数据源：** {source_text}\n⏰ **处理时间：** {now.strftime('%Y-%m-%d %H:%M:%S')}",
                    "tag": "lark_md"
                }
            }
        ])

        # 添加分隔线
        card["elements"].append({
            "tag": "hr"
        })

        # 如果有API结果数据，展示详细统计
        if api_result and api_result.get('success') and api_result.get('data'):
            data = api_result['data']

            # 处理统计信息
            if 'processing_stats' in data:
                stats = data['processing_stats']
                total_videos = data.get('total_videos', 0)
                total_minutes = stats.get('total_minutes', 0)

                # 总体统计
                hours = total_minutes // 60
                minutes = total_minutes % 60
                time_display = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

                card["elements"].append({
                    "tag": "div",
                    "text": {
                        "content": f"📊 **总体统计：** {total_videos} 个视频，总时长 {time_display}",
                        "tag": "lark_md"
                    }
                })

                # 优先级分布（使用饼图）
                if 'priority_stats' in stats and total_videos > 0:
                    priority_stats = stats['priority_stats']

                    # 定义优先级排序（确保按High→Medium→Low→None顺序显示）
                    priority_order = ['😍高', '😜中', '😐低', '😶无']
                    # 也支持英文优先级名
                    priority_order_en = ['High', 'Medium', 'Low', 'None']

                    # 构建饼图数据（官方格式，按优先级排序）
                    chart_data = []

                    # 按照定义的顺序处理优先级
                    all_priorities = list(priority_stats.keys())
                    ordered_priorities = []

                    # 先添加预定义顺序中存在的优先级
                    for priority in priority_order + priority_order_en:
                        if priority in all_priorities:
                            ordered_priorities.append(priority)
                            all_priorities.remove(priority)

                    # 再添加其他未预定义的优先级
                    ordered_priorities.extend(all_priorities)

                    for priority in ordered_priorities:
                        if priority in priority_stats:
                            info = priority_stats[priority]
                            count = info.get('count', 0)
                            total_mins = info.get('total_minutes', 0)
                            percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                            # 时长格式化
                            p_hours = total_mins // 60
                            p_minutes = total_mins % 60
                            p_time_display = f"{p_hours}h{p_minutes}m" if p_hours > 0 else f"{p_minutes}m"

                            chart_data.append({
                                "type": f"{priority} {percentage}%",
                                "value": str(count)
                            })

                    # 添加优先级分布饼图
                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "🎯 **优先级分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "优先级分布"
                                },
                                "data": {
                                    "values": chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 类型分布（使用环状图）
                if 'category_stats' in stats and total_videos > 0:
                    category_stats = stats['category_stats']

                    # 构建环状图数据（官方格式，添加百分比）
                    category_chart_data = []
                    for category, info in category_stats.items():
                        count = info.get('count', 0)
                        total_mins = info.get('total_minutes', 0)
                        percentage = round((count / total_videos) * 100, 1) if total_videos > 0 else 0

                        c_hours = total_mins // 60
                        c_minutes = total_mins % 60
                        c_time_display = f"{c_hours}h{c_minutes}m" if c_hours > 0 else f"{c_minutes}m"

                        category_chart_data.append({
                            "type": f"{category} {percentage}%",
                            "value": str(count)
                        })

                    card["elements"].extend([
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": "📂 **类型分布**",
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "chart",
                            "aspect_ratio": "4:3",
                            "chart_spec": {
                                "type": "pie",
                                "title": {
                                    "text": "类型分布"
                                },
                                "data": {
                                    "values": category_chart_data
                                },
                                "valueField": "value",
                                "categoryField": "type",
                                "outerRadius": 0.7,
                                "innerRadius": 0.3,
                                "legends": {
                                    "visible": True,
                                    "orient": "bottom",
                                    "maxRow": 3,
                                    "itemWidth": 80,
                                    "itemGap": 8
                                },
                                "label": {
                                    "visible": True
                                },
                                "padding": {
                                    "left": 10,
                                    "top": 10,
                                    "bottom": 80,
                                    "right": 10
                                }
                            }
                        }
                    ])

                # 新旧视频分布（使用对比饼图）
                if 'new_old_stats' in stats:
                    new_old = stats['new_old_stats']
                    new_count = new_old.get('new_videos', 0)
                    old_count = new_old.get('old_videos', 0)
                    new_minutes = new_old.get('new_total_minutes', 0)
                    old_minutes = new_old.get('old_total_minutes', 0)

                    if new_count + old_count > 0:
                        total_count = new_count + old_count
                        new_percentage = round((new_count / total_count) * 100, 1) if total_count > 0 else 0
                        old_percentage = round((old_count / total_count) * 100, 1) if total_count > 0 else 0

                        new_old_data = [
                            {
                                "type": f"新视频(48h内) {new_percentage}%",
                                "value": str(new_count)
                            },
                            {
                                "type": f"旧视频(48h外) {old_percentage}%",
                                "value": str(old_count)
                            }
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "🕒 **新旧视频分布**",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "新旧视频分布"
                                    },
                                    "data": {
                                        "values": new_old_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                # 广告检测统计（使用对比饼图）
                if 'ad_timestamp_stats' in stats:
                    ad_stats = stats['ad_timestamp_stats']
                    ad_count = ad_stats.get('videos_with_ads', 0)
                    no_ad_count = ad_stats.get('videos_without_ads', 0)
                    ad_percentage_global = ad_stats.get('ads_percentage', 0)
                    avg_ad_duration = ad_stats.get('avg_ad_duration_seconds', 0)

                    if ad_count + no_ad_count > 0:
                        total_ad_count = ad_count + no_ad_count
                        ad_percentage = round((ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0
                        no_ad_percentage = round((no_ad_count / total_ad_count) * 100, 1) if total_ad_count > 0 else 0

                        ad_data = [
                            {"type": f"含广告 {ad_percentage}%", "value": str(ad_count)},
                            {"type": f"无广告 {no_ad_percentage}%", "value": str(no_ad_count)}
                        ]

                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": f"📺 **广告检测** (检测到{ad_percentage_global:.1f}%包含广告)",
                                    "tag": "lark_md"
                                }
                            },
                            {
                                "tag": "chart",
                                "aspect_ratio": "4:3",
                                "chart_spec": {
                                    "type": "pie",
                                    "title": {
                                        "text": "广告检测分布"
                                    },
                                    "data": {
                                        "values": ad_data
                                    },
                                    "valueField": "value",
                                    "categoryField": "type",
                                    "outerRadius": 0.7,
                                    "legends": {
                                        "visible": True,
                                        "orient": "bottom",
                                        "maxRow": 3,
                                        "itemWidth": 80,
                                        "itemGap": 8
                                    },
                                    "label": {
                                        "visible": True
                                    },
                                    "padding": {
                                        "left": 10,
                                        "top": 10,
                                        "bottom": 80,
                                        "right": 10
                                    }
                                }
                            }
                        ])

                        if avg_ad_duration > 0:
                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"💡 平均广告时长: {int(avg_ad_duration)}秒",
                                    "tag": "lark_md"
                                }
                            })

                # 作者排行（文本显示，图表对名字太长不友好）
                if 'author_stats' in stats and stats['author_stats']:
                    author_stats = stats['author_stats'][:5]  # 只显示前5名
                    if author_stats:
                        card["elements"].extend([
                            {
                                "tag": "hr"
                            },
                            {
                                "tag": "div",
                                "text": {
                                    "content": "👤 **作者排行** (前5名)",
                                    "tag": "lark_md"
                                }
                            }
                        ])

                        for i, author in enumerate(author_stats, 1):
                            name = author.get('name', '未知')
                            count = author.get('count', 0)
                            total_mins = author.get('total_minutes', 0)
                            a_time_display = f"{total_mins//60}h{total_mins%60}m" if total_mins//60 > 0 else f"{total_mins}m"

                            card["elements"].append({
                                "tag": "div",
                                "text": {
                                    "content": f"{i}. **{name}:** {count}个视频 ({a_time_display})",
                                    "tag": "lark_md"
                                }
                            })

            # 显示处理结果概要
            card["elements"].extend([
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "💡 点击菜单中的\"B站\"获取最新无广告的视频",
                        "tag": "lark_md"
                    }
                }
            ])
        else:
            # 没有详细数据时的简化显示
            card["elements"].append({
                "tag": "div",
                "text": {
                    "content": "**📋 处理完成**\n\n系统已自动处理B站数据源，新内容已添加到数据库。",
                    "tag": "lark_md"
                }
            })

        return card

    @require_service('notion', "标记服务暂时不可用")
    @safe_execute("定时卡片标记已读失败")
    def handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理定时卡片中的标记B站视频为已读
        """
        # 获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

        # 获取参数
        pageid = action_value.get("pageid", "")
        video_index = action_value.get("video_index", 0)

        if not pageid:
            return ProcessResult.error_result("缺少页面ID，无法标记为已读")

        # 执行标记为已读操作
        success = notion_service.mark_video_as_read(pageid)
        if not success:
            return ProcessResult.error_result("标记为已读失败")

        # 定时卡片：基于原始数据重构，只更新已读状态，不重新获取统计数据
        try:
            original_analysis_data = action_value.get("original_analysis_data")
            if original_analysis_data:
                # 创建日报业务实例并使用原始数据重新生成卡片
                daily_summary_business = DailySummaryBusiness(app_controller=self.app_controller)
                updated_card = daily_summary_business.create_daily_summary_card(original_analysis_data)

                return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
                    "toast": {
                        "type": "success",
                        "content": f"已标记第{video_index + 1}个推荐为已读"
                    },
                    "card": {
                        "type": "raw",
                        "data": updated_card
                    }
                })
            else:
                # 如果没有原始数据，降级处理
                return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
                    "toast": {
                        "type": "success",
                        "content": f"已标记第{video_index + 1}个推荐为已读"
                    }
                })
        except Exception as e:
            # 如果重新生成失败，只返回toast
            debug_utils.log_and_print(f"❌ 重新生成定时卡片失败: {str(e)}", log_level="ERROR")
            return ProcessResult.success_result(ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON, {
                "toast": {
                    "type": "success",
                    "content": f"已标记第{video_index + 1}个推荐为已读"
                }
            })

    def _get_admin_id(self) -> Optional[str]:
        """获取管理员ID"""
        if self.app_controller:
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            if config_service:
                return config_service.get("ADMIN_ID", None)
        return None

    @safe_execute("个人状态评估消息创建失败")
    def personal_status_evaluation(self, status_data: Dict[str, Any], evaluation_time: str) -> ProcessResult:
        """
        创建个人状态评估消息

        Args:
            status_data: 状态数据
            evaluation_time: 评估时间

        Returns:
            ProcessResult: 处理结果
        """
        # 添加到信息聚合服务，避免直接发送
        admin_id = self._get_admin_id()
        if admin_id and self.app_controller:
            aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
            if aggregation_service:
                aggregation_service.add_message(
                    source_type="personal_status_eval",
                    content={
                        "evaluation_time": evaluation_time,
                        "status_data": status_data,
                        "summary": self._format_status_summary(status_data)
                    },
                    user_id=admin_id,
                    priority=MessagePriority.LOW
                )

                return ProcessResult.success_result("no_reply", {
                    "message": "个人状态评估已加入汇总队列"
                })

        # 降级处理：直接返回状态信息
        return ProcessResult.success_result("text", self._format_status_summary(status_data))

    def _format_status_summary(self, status_data: Dict[str, Any]) -> str:
        """格式化状态摘要"""
        if not status_data:
            return "📊 个人状态评估：暂无数据"

        summary_parts = ["📊 **个人状态评估**\n"]

        # 系统健康状态
        system_health = status_data.get("system_health", {})
        if system_health:
            overall_status = system_health.get("overall_status", "unknown")
            healthy_services = system_health.get("healthy_services", 0)
            service_count = system_health.get("service_count", 0)

            summary_parts.append(f"🔧 **系统状态**: {overall_status}")
            summary_parts.append(f"⚙️ **服务健康**: {healthy_services}/{service_count}")

        # 待处理任务
        pending_tasks = status_data.get("pending_tasks", {})
        if pending_tasks:
            total_ops = pending_tasks.get("total_operations", 0)
            pending_count = pending_tasks.get("pending_count", 0)
            summary_parts.append(f"📋 **待处理任务**: {pending_count}/{total_ops}")

        return "\n".join(summary_parts)

    @safe_execute("周度盘点消息创建失败")
    def weekly_review(self, weekly_data: Dict[str, Any], review_week: str) -> ProcessResult:
        """
        创建周度盘点消息

        Args:
            weekly_data: 周度数据
            review_week: 评估周期

        Returns:
            ProcessResult: 处理结果
        """
        # 添加到信息聚合服务
        admin_id = self._get_admin_id()
        if admin_id and self.app_controller:
            aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
            if aggregation_service:
                aggregation_service.add_message(
                    source_type="weekly_review",
                    content={
                        "review_week": review_week,
                        "weekly_data": weekly_data,
                        "summary": self._format_weekly_summary(weekly_data, review_week)
                    },
                    user_id=admin_id,
                    priority=MessagePriority.NORMAL
                )

                return ProcessResult.success_result("no_reply", {
                    "message": "周度盘点已加入汇总队列"
                })

        # 降级处理：直接返回盘点信息
        return ProcessResult.success_result("text", self._format_weekly_summary(weekly_data, review_week))

    def _format_weekly_summary(self, weekly_data: Dict[str, Any], review_week: str) -> str:
        """格式化周度摘要"""
        if not weekly_data:
            return f"📅 {review_week}周度盘点：暂无数据"

        summary_parts = [f"📅 **{review_week}周度盘点**\n"]

        # 成果亮点
        achievements = weekly_data.get("achievement_highlights", [])
        if achievements:
            summary_parts.append("🎯 **本周亮点**:")
            for achievement in achievements[:3]:  # 最多3个
                summary_parts.append(f"• {achievement}")

        # 系统统计
        system_stats = weekly_data.get("system_statistics", {})
        if system_stats:
            summary_parts.append(f"\n⚙️ **系统概况**: {len(system_stats)}个服务正常运行")

        # 下周关注
        upcoming_focus = weekly_data.get("upcoming_focus", [])
        if upcoming_focus:
            summary_parts.append("\n🔜 **下周关注**:")
            for focus in upcoming_focus[:2]:  # 最多2个
                summary_parts.append(f"• {focus}")

        return "\n".join(summary_parts)

    @safe_execute("月度盘点消息创建失败")
    def monthly_review(self, monthly_data: Dict[str, Any], review_month: str) -> ProcessResult:
        """
        创建月度盘点消息

        Args:
            monthly_data: 月度数据
            review_month: 评估月份

        Returns:
            ProcessResult: 处理结果
        """
        # 添加到信息聚合服务
        admin_id = self._get_admin_id()
        if admin_id and self.app_controller:
            aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
            if aggregation_service:
                aggregation_service.add_message(
                    source_type="monthly_review",
                    content={
                        "review_month": review_month,
                        "monthly_data": monthly_data,
                        "summary": self._format_monthly_summary(monthly_data, review_month)
                    },
                    user_id=admin_id,
                    priority=MessagePriority.HIGH
                )

                return ProcessResult.success_result("no_reply", {
                    "message": "月度盘点已加入汇总队列"
                })

        # 降级处理：直接返回盘点信息
        return ProcessResult.success_result("text", self._format_monthly_summary(monthly_data, review_month))

    def _format_monthly_summary(self, monthly_data: Dict[str, Any], review_month: str) -> str:
        """格式化月度摘要"""
        if not monthly_data:
            return f"📊 {review_month}月度盘点：暂无数据"

        summary_parts = [f"📊 **{review_month}月度盘点**\n"]

        # 关键成就
        key_achievements = monthly_data.get("key_achievements", [])
        if key_achievements:
            summary_parts.append("🏆 **关键成就**:")
            for achievement in key_achievements[:3]:  # 最多3个
                summary_parts.append(f"• {achievement}")

        # 系统演进
        system_evolution = monthly_data.get("system_evolution", {})
        if system_evolution:
            current_health = system_evolution.get("current_health", "unknown")
            architecture = system_evolution.get("architecture_maturity", "持续发展")
            summary_parts.append(f"\n🔧 **系统状态**: {current_health}")
            summary_parts.append(f"🏗️ **架构成熟度**: {architecture}")

        # 下月目标
        next_goals = monthly_data.get("next_month_goals", [])
        if next_goals:
            summary_parts.append("\n🎯 **下月目标**:")
            for goal in next_goals[:3]:  # 最多3个
                summary_parts.append(f"• {goal}")

        return "\n".join(summary_parts)
