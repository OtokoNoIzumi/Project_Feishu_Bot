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
        # 构建B站信息cache分析数据
        analysis_data = self.build_bilibili_cache_analysis()

        # 获取运营数据
        operation_data = self.get_operation_data()
        if operation_data:
            analysis_data['operation_data'] = operation_data

        # 将服务状态信息加入分析数据
        if services_status:
            analysis_data['services_status'] = services_status

        card_content = self.create_daily_summary_card(analysis_data)

        return ProcessResult.success_result("interactive", card_content)

    def build_bilibili_cache_analysis(self) -> Dict[str, Any]:
        """
        构建B站信息cache分析数据（获取统计信息用于7:30定时任务）
        """
        now = datetime.now()

        # 尝试从notion服务获取B站视频统计数据
        if self.app_controller:
            notion_service = self.app_controller.get_service(ServiceNames.NOTION)
            if notion_service:
                try:
                    # 调用统计方法获取B站数据分析
                    stats = notion_service.get_bili_videos_statistics()
                    # 兼容新版返回格式
                    if stats and stats.get("success", False):
                        # 兼容字段映射
                        total_count = stats.get("总未读数", 0)
                        priority_stats = stats.get("优先级统计", {})
                        duration_stats = stats.get("时长分布", {})
                        source_stats = stats.get("来源统计", {})
                        top_recommendations = stats.get("今日精选推荐", [])
                        return {
                            "date": now.strftime("%Y年%m月%d日"),
                            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                            "statistics": {
                                "total_count": total_count,
                                "priority_stats": priority_stats,
                                "duration_stats": duration_stats,
                                "source_stats": source_stats,
                                "top_recommendations": top_recommendations
                            },
                            "source": "notion_statistics",
                            "timestamp": now.isoformat()
                        }
                except Exception as e:
                    debug_utils.log_and_print(f"获取notion B站统计数据失败: {e}", log_level="WARNING")

        # 基础状态信息作为fallback
        return {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "status": "目前没有待看的B站视频",
            "source": "placeholder",
            "timestamp": now.isoformat()
        }

    def get_operation_data(self) -> Optional[Dict[str, Any]]:
        """
        获取运营数据（每日必须，周一还要获取周数据）
        """
        now = datetime.now()
        today_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        is_monday = now.weekday() == 0  # 0是周一

        # 检查B站API是否可用
        if not self._is_bili_api_available():
            debug_utils.log_and_print("B站API不可用，跳过运营数据获取", log_level="WARNING")
            return None

        try:
            # 获取每日数据
            daily_data = self._get_daily_operation_data(today_str)

            operation_data = {
                "daily": daily_data,
                "date": today_str,
                "is_monday": is_monday
            }

            # 如果是周一，额外获取周数据
            if is_monday:
                weekly_data = self._get_weekly_operation_data()
                if weekly_data:
                    operation_data["weekly"] = weekly_data

            return operation_data

        except Exception as e:
            debug_utils.log_and_print(f"获取运营数据失败: {e}", log_level="ERROR")
            return None

    def _is_bili_api_available(self) -> bool:
        """检查B站API是否可用"""
        return (self.bili_api_base_url and
                self.bili_api_base_url != DefaultValues.DEFAULT_BILI_API_BASE)

    def _get_daily_operation_data(self, date: str) -> Optional[Dict[str, Any]]:
        """获取每日运营数据"""
        try:
            # 在线程池中执行异步API调用
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_async_in_thread, self._call_daily_operation_api_async, date)
                success, response_data = future.result(timeout=30)

            if success and response_data.get("success", False):
                return response_data
            else:
                error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
                debug_utils.log_and_print(f"获取每日运营数据失败: {error_msg}", log_level="WARNING")
                return None

        except Exception as e:
            debug_utils.log_and_print(f"获取每日运营数据异常: {e}", log_level="ERROR")
            return None

    def _get_weekly_operation_data(self) -> Optional[Dict[str, Any]]:
        """获取每周运营数据"""
        try:
            # 在线程池中执行异步API调用
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_async_in_thread, self._call_weekly_operation_api_async)
                success, response_data = future.result(timeout=30)

            if success and response_data.get("success", False):
                return response_data
            else:
                error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
                debug_utils.log_and_print(f"获取每周运营数据失败: {error_msg}", log_level="WARNING")
                return None

        except Exception as e:
            debug_utils.log_and_print(f"获取每周运营数据异常: {e}", log_level="ERROR")
            return None

    def _run_async_in_thread(self, async_func, *args):
        """在线程中运行异步函数"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(async_func(*args))
            finally:
                loop.close()
        except Exception as e:
            debug_utils.log_and_print(f"异步函数执行失败: {e}", log_level="ERROR")
            return False, {"message": str(e)}

    async def _call_daily_operation_api_async(self, date: str) -> Tuple[bool, Dict[str, Any]]:
        """异步调用每日运营数据API"""
        url = f"{self.bili_api_base_url}/api/admin/operation/daily"
        data = {
            "date": date,
            "with_comparison": True,
            "admin_secret_key": self.bili_admin_secret
        }
        return await self._make_operation_api_request(url, data, "每日运营数据")

    async def _call_weekly_operation_api_async(self) -> Tuple[bool, Dict[str, Any]]:
        """异步调用每周运营数据API"""
        url = f"{self.bili_api_base_url}/api/admin/operation/weekly"
        params = {
            "admin_secret_key": self.bili_admin_secret
            # week_start 留空，使用默认值
        }
        return await self._make_operation_api_request(url, params, "每周运营数据", method="GET")

    async def _make_operation_api_request(
        self,
        url: str,
        data: Dict[str, Any],
        operation_name: str,
        method: str = "POST",
        max_retries: int = 2,
        retry_delay: float = 1.0
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        通用的运营数据API请求方法

        Args:
            url: API端点URL
            data: 请求数据
            operation_name: 操作名称（用于日志）
            method: HTTP方法（GET或POST）
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            Tuple[bool, Dict[str, Any]]: (是否成功, 响应数据)
        """
        headers = {"Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=15)

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    if method.upper() == "GET":
                        async with session.get(url, params=data, headers=headers) as response:
                            response_data = await response.json()
                    else:  # POST
                        async with session.post(url, data=json.dumps(data), headers=headers) as response:
                            response_data = await response.json()

                    if response.status == 200:
                        debug_utils.log_and_print(f"✅ {operation_name}获取成功", log_level="INFO")
                        return True, response_data
                    else:
                        error_msg = f"HTTP {response.status}: {response_data.get('message', '未知错误')}"
                        debug_utils.log_and_print(f"❌ {operation_name}API返回错误: {error_msg}", log_level="WARNING")
                        return False, {"message": error_msg}

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    debug_utils.log_and_print(f"⚠️ {operation_name}API调用失败，第{attempt + 1}次重试: {e}", log_level="WARNING")
                    await asyncio.sleep(retry_delay)
                else:
                    debug_utils.log_and_print(f"❌ {operation_name}API调用最终失败: {e}", log_level="ERROR")

        return False, {"message": str(last_error) if last_error else "API调用失败"}

    def create_daily_summary_card(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        source = analysis_data.get('source', 'unknown')

        if source == 'notion_statistics':
            # notion服务提供的B站分析数据
            content = self.format_notion_bili_analysis(analysis_data)
        else:
            # 占位信息
            content = f"📊 **{analysis_data['date']} {analysis_data['weekday']}** \n\n🔄 **系统状态**\n\n{analysis_data.get('status', '服务准备中...')}"

        # 添加运营数据信息
        operation_data = analysis_data.get('operation_data')
        if operation_data:
            content += self.format_operation_data(operation_data)

        # 添加服务状态信息
        services_status = analysis_data.get('services_status')
        if services_status:
            content += self.format_services_status(services_status)

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": content,
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "📊 每日信息汇总",
                    "tag": "plain_text"
                }
            }
        }

        # 如果有推荐视频，添加推荐链接部分
        if source == 'notion_statistics':
            statistics = analysis_data.get('statistics', {})

            # 兼容新版字段名
            top_recommendations = statistics.get('top_recommendations', None)
            if top_recommendations is None:
                top_recommendations = statistics.get('今日精选推荐', [])

            if top_recommendations:
                # 获取notion服务以检查已读状态
                notion_service = None
                if hasattr(self, 'app_controller') and self.app_controller:
                    notion_service = self.app_controller.get_service('notion')

                # 添加推荐视频标题
                card["elements"].extend([
                    {
                        "tag": "div",
                        "text": {
                            "content": "🎬 **今日精选推荐**",
                            "tag": "lark_md"
                        }
                    }
                ])

                # 添加每个推荐视频的简化展示
                for i, video in enumerate(top_recommendations, 1):
                    # 检查该视频是否已读（兼容新旧字段）
                    video_pageid = video.get('页面ID', video.get('pageid', ''))
                    video_read = notion_service.is_video_read(video_pageid) if notion_service and video_pageid else False

                    # 视频标题（兼容新旧字段）
                    title = video.get('标题', video.get('title', '无标题视频'))
                    if len(title) > 30:
                        title = title[:30] + "..."

                    # 兼容新旧字段格式
                    priority = video.get('优先级', video.get('chinese_priority', '未知'))
                    duration = video.get('时长', video.get('duration_str', '未知'))

                    card["elements"].append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{title}** | 优先级: {priority} • 时长: {duration}{' | 已读' if video_read else ''}"
                        }
                    })

                    # 视频基本信息和链接按钮
                    video_url = video.get('链接', video.get('url', ''))
                    card["elements"].append({
                        "tag": "action",
                        "layout": "flow",  # 使用flow布局让按钮在一行显示
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "📺 B站"
                                },
                                "type": "default",
                                "size": "tiny",
                                "behaviors": [
                                    {
                                        "type": "open_url",
                                        "default_url": video_url,
                                        "pc_url": video_url,
                                        "ios_url": video_url,
                                        "android_url": convert_to_bili_app_link(video_url)
                                    }
                                ]
                            }
                        ] + ([] if video_read else [{
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "✅ 已读"
                            },
                            "type": "primary",
                            "size": "tiny",
                            "value": {
                                "card_action": "mark_bili_read",
                                "pageid": video_pageid,
                                "card_type": "daily",  # 定时卡片
                                "video_index": i - 1,  # 推荐视频序号 (0,1,2)
                                # 保存原始完整数据用于卡片重构（不重新获取统计数据）
                                "original_analysis_data": analysis_data
                            }
                        }] if video_pageid else [])
                    })

        return card

    def format_notion_bili_analysis(self, data: Dict[str, Any]) -> str:
        """格式化notion B站统计数据"""
        content = f"📊 **{data['date']} {data['weekday']}**"
        content += "\n\n🎯 **B站信息分析汇总**"

        statistics = data.get('statistics', {})

        # 总体统计
        total_count = statistics.get('total_count', None)
        # 兼容新版字段
        if total_count is None:
            total_count = statistics.get('总未读数', 0)
        content += f"\n\n📈 **总计:** {total_count} 个未读视频"

        if total_count > 0:
            # 优先级统计（增加时长总计）
            priority_stats = statistics.get('priority_stats', None)
            if priority_stats is None:
                priority_stats = statistics.get('优先级统计', {})
            if priority_stats:
                content += "\n\n🎯 **优先级分布:**"
                for priority, info in priority_stats.items():
                    # 新版格式：{'😜中': {'数量': 1, '总时长分钟': 51}}
                    count = info.get('数量', info.get('count', 0))
                    total_minutes = info.get('总时长分钟', info.get('total_minutes', 0))
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
                    content += f"\n• {priority}: {count} 个 ({time_str})"

            # 时长分布
            duration_stats = statistics.get('duration_stats', None)
            if duration_stats is None:
                duration_stats = statistics.get('时长分布', {})
            if duration_stats:
                content += "\n\n⏱️ **时长分布:**"
                for duration_type, count in duration_stats.items():
                    content += f"\n• {duration_type}: {count} 个"

            # 来源统计
            source_stats = statistics.get('source_stats', None)
            if source_stats is None:
                source_stats = statistics.get('来源统计', {})
            if source_stats:
                content += "\n\n📺 **来源分布:**"
                for source, count in source_stats.items():
                    content += f"\n• {source}: {count} 个"

        return content

    def format_operation_data(self, operation_data: Dict[str, Any]) -> str:
        """格式化运营数据信息"""
        content = "\n\n📈 **运营日报**"

        # 获取每日数据
        daily = operation_data.get('daily')
        is_monday = operation_data.get('is_monday', False)

        if daily and daily.get('success', False):
            current = daily.get('current', {})
            previous = daily.get('previous', {})
            comparison = daily.get('comparison', {})

            # 基础统计信息
            date_str = current.get('stats_date', '未知日期')
            content += f"\n📅 **{date_str} 数据概览**"

            # 用户活跃度
            active_users = current.get('active_users', 0)
            new_users = current.get('new_users', 0)
            content += f"\n👥 **用户活跃度:** {active_users} 活跃用户 (+{new_users} 新增)"

            # 内容统计
            new_videos_user = current.get('new_videos_user', 0)
            new_videos_admin = current.get('new_videos_admin', 0)
            total_requests = current.get('total_user_requests', 0)
            content += f"\n🎬 **内容统计:** {new_videos_user} 用户视频 | {new_videos_admin} 管理员视频"
            content += f"\n🔄 **请求总数:** {total_requests} 次"

            # 缓存效率
            cache_hits = current.get('cache_hits', 0)
            cache_rate = current.get('cache_utilization_rate', 0)
            content += f"\n⚡ **缓存效率:** {cache_hits} 次命中 ({cache_rate:.1%})"

            # 拒绝统计
            total_rejections = current.get('total_rejections', 0)
            rejected_users = current.get('rejected_users', 0)
            if rejected_users > 0:
                rejected_rate = total_rejections / rejected_users
                content += f"\n🚫 **拒绝请求:** {total_rejections} 次 ({rejected_users} 用户，人均 {rejected_rate:.1f} 次)"
            else:
                content += f"\n🚫 **拒绝请求:** {total_rejections} 次 ({rejected_users} 用户)"

            # 显示关键变化趋势
            if comparison:
                trends = []

                # 检查用户活跃度变化
                if 'active_users' in comparison:
                    change = comparison['active_users'].get('change', 0)
                    trend = comparison['active_users'].get('trend', '')
                    if abs(change) >= 5:  # 显著变化
                        trend_emoji = '📈' if trend == 'up' else '📉'
                        trends.append(f"活跃用户{trend_emoji}{abs(change)}")

                # 检查请求量变化
                if 'total_user_requests' in comparison:
                    change = comparison['total_user_requests'].get('change', 0)
                    trend = comparison['total_user_requests'].get('trend', '')
                    if abs(change) >= 20:  # 显著变化
                        trend_emoji = '📈' if trend == 'up' else '📉'
                        trends.append(f"请求量{trend_emoji}{abs(change)}")

                if trends:
                    content += f"\n📊 **今日变化:** {' | '.join(trends)}"

            # 广告检测统计（如果有）
            ads_detected = current.get('ads_detected', 0)
            total_ad_duration = current.get('total_ad_duration', 0)
            ad_rate = ads_detected / total_requests if total_requests > 0 else 0
            if ads_detected > 0:
                ad_minutes = int(total_ad_duration / 60) if total_ad_duration else 0
                content += f"\n🎯 **广告检测:** {ads_detected} 个广告，总时长 {ad_minutes} 分钟，占比 {ad_rate:.1%}"

        # 如果是周一，添加周报数据
        if is_monday:
            weekly = operation_data.get('weekly')
            if weekly and weekly.get('success', False):
                content += self.format_weekly_operation_data(weekly.get('data', {}))

        return content

    def format_weekly_operation_data(self, weekly_data: Dict[str, Any]) -> str:
        """格式化周运营数据"""
        content = "\n\n📅 **本周运营概览**"

        # 周期信息
        week_start = weekly_data.get('week_start_date', '')
        week_end = weekly_data.get('week_end_date', '')
        if week_start and week_end:
            content += f"\n🗓️ **统计周期:** {week_start} 至 {week_end}"

        # 用户统计
        total_users = weekly_data.get('total_users', 0)
        weekly_new_users = weekly_data.get('weekly_new_users', 0)
        weekly_churned_users = weekly_data.get('weekly_churned_users', 0)
        active_users = weekly_data.get('active_users', 0)
        content += f"\n👥 **用户概况:** {total_users} 总用户 | {active_users} 活跃 | +{weekly_new_users} 新增 | -{weekly_churned_users} 流失"

        # 付费用户
        free_users = weekly_data.get('free_users', 0)
        paid_users = weekly_data.get('paid_users', 0)
        if paid_users > 0:
            paid_rate = paid_users / (free_users + paid_users) * 100 if (free_users + paid_users) > 0 else 0
            content += f"\n💰 **付费情况:** {paid_users} 付费用户 ({paid_rate:.1f}%)"

        # 内容分析
        weekly_unique_videos = weekly_data.get('weekly_unique_videos', 0)
        weekly_requests = weekly_data.get('weekly_total_requests', 0)
        cache_rate = weekly_data.get('weekly_cache_utilization_rate', 0)
        content += f"\n📊 **内容活动:** {weekly_unique_videos} 视频 | {weekly_requests} 请求 | 缓存命中率 {cache_rate:.1%}"

        # 广告分析
        weekly_ad_videos = weekly_data.get('weekly_ad_videos', 0)
        weekly_ad_time_ratio = weekly_data.get('weekly_ad_time_ratio', 0)
        if weekly_ad_videos > 0:
            content += f"\n🎯 **广告分析:** {weekly_ad_videos} 个广告视频 ({weekly_ad_time_ratio:.2%} 时长占比)"

        return content

    def format_services_status(self, services_status: Dict[str, Any]) -> str:
        """格式化服务状态信息"""
        content = "\n\n🔧 **外部服务状态检测**"
        check_time = services_status.get('check_time', '未知时间')
        content += f"\n检测时间: {check_time}"

        services = services_status.get('services', {})

        # B站API服务状态
        bili_api = services.get('bilibili_api', {})
        if bili_api.get('enabled', False):
            status = bili_api.get('status', 'unknown')
            message = bili_api.get('message', '')
            response_time = bili_api.get('response_time', '')
            url = bili_api.get('url', '')

            status_emoji = {
                'healthy': '✅',
                'warning': '⚠️',
                'error': '❌',
                'disabled': '⏸️'
            }.get(status, '❓')

            content += f"\n\n{status_emoji} **{bili_api.get('service_name', 'B站API服务')}**"
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != 'error':
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"
        else:
            content += "\n\n⏸️ **B站API服务**: 未启用"

        # Gradio服务状态
        gradio = services.get('gradio', {})
        if gradio.get('enabled', False):
            status = gradio.get('status', 'unknown')
            message = gradio.get('message', '')
            response_time = gradio.get('response_time', '')
            url = gradio.get('url', '')

            status_emoji = {
                'healthy': '✅',
                'warning': '⚠️',
                'error': '❌',
                'disabled': '⏸️'
            }.get(status, '❓')

            content += f"\n\n{status_emoji} **{gradio.get('service_name', 'Gradio图像服务')}**"
            content += f"\n状态: {message}"
            if response_time:
                content += f" ({response_time})"
            if url and status != 'error':
                # 截断长URL显示
                display_url = url if len(url) <= 40 else url[:37] + "..."
                content += f"\n地址: {display_url}"

            # 显示令牌信息
            token_info = gradio.get('token_info', {})
            if token_info.get('has_token', False):
                token_status = token_info.get('status', 'unknown')
                if token_status == 'valid':
                    expires_in_hours = token_info.get('expires_in_hours', 0)
                    expires_at = token_info.get('expires_at', '')
                    # 格式化时间为 mm-dd hh:mm
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            # 兼容带时区的ISO格式
                            from datetime import datetime
                            if "+" in expires_at or "Z" in expires_at:
                                # 去掉时区信息
                                expires_at_clean = expires_at.split("+")[0].replace("Z", "")
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
                elif token_status == 'expired':
                    expires_at = token_info.get('expires_at', '')
                    formatted_expires_at = ""
                    if expires_at:
                        try:
                            from datetime import datetime
                            if "+" in expires_at or "Z" in expires_at:
                                expires_at_clean = expires_at.split("+")[0].replace("Z", "")
                            else:
                                expires_at_clean = expires_at
                            dt = datetime.fromisoformat(expires_at_clean)
                            formatted_expires_at = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            formatted_expires_at = expires_at
                    content += f"\n❌ 令牌已于{formatted_expires_at}过期，需要更新"
                elif token_status == 'parse_error':
                    content += "\n⚠️ 令牌时间解析异常"
                elif token_status == 'no_expiry_info':
                    content += "\n🔑 令牌已配置 (无过期信息)"
        else:
            content += "\n\n⏸️ **Gradio图像服务**: 未启用"

        return content

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
                # 使用原始数据重新生成卡片，已读状态会自动更新
                updated_card = self.create_daily_summary_card(original_analysis_data)

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
