"""
每日信息汇总业务

处理每日信息汇总的完整业务逻辑，包括：
1. B站信息分析数据构建
2. 运营数据获取与处理
3. 日报卡片生成
4. 用户权限验证
"""

import json
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import random

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames, DefaultValues, EnvVars
from Module.Business.processors.base_processor import BaseProcessor, ProcessResult, safe_execute
from Module.Business.processors.bilibili_processor import convert_to_bili_app_link


class DailySummaryBusiness(BaseProcessor):
    """
    每日信息汇总业务

    负责处理每日信息汇总的完整业务流程
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

    @safe_execute("创建每日信息汇总失败")
    def create_daily_summary(self, services_status: Dict[str, Any] = None) -> ProcessResult:
        """
        创建每日信息汇总消息（主业务入口）

        Args:
            user_id: 用户ID
            services_status: 服务状态信息

        Returns:
            ProcessResult: 处理结果
        """
        # 构建B站信息cache分析数据（整合原来的分散逻辑）
        analysis_data = self.build_bilibili_analysis_data()

        # 获取运营数据
        operation_data = self.get_operation_data()
        if operation_data:
            analysis_data['operation_data'] = operation_data

        # 将服务状态信息加入分析数据
        if services_status:
            analysis_data['services_status'] = services_status

        card_content = self.create_daily_summary_card(analysis_data)

        return ProcessResult.user_list_result("interactive", card_content)

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
                    # 直接获取缓存数据，不调用统计方法
                    videos = notion_service.cache_data.get(notion_service.bili_cache_key, [])
                    unread_videos = [v for v in videos if v.get("unread", True)]

                    if unread_videos:
                        # 统计各维度数据（复制自get_bili_videos_statistics逻辑）
                        priority_stats = {}
                        duration_stats = {"短视频": 0, "中视频": 0, "长视频": 0}  # ≤10分钟, 10-30分钟, >30分钟
                        source_stats = {}

                        for video in unread_videos:
                            # 优先级统计
                            priority = video.get("chinese_priority", "Unknown")
                            if priority not in priority_stats:
                                priority_stats[priority] = {"数量": 0, "总时长分钟": 0}

                            priority_stats[priority]["数量"] += 1

                            # 获取时长（分钟）
                            duration_minutes = video.get("duration", 0)
                            try:
                                total_minutes = float(duration_minutes) if duration_minutes else 0
                                priority_stats[priority]["总时长分钟"] += int(total_minutes)
                            except (ValueError, TypeError):
                                total_minutes = 0

                            # 时长统计
                            if total_minutes <= 10:
                                duration_stats["短视频"] += 1
                            elif total_minutes <= 30:
                                duration_stats["中视频"] += 1
                            else:
                                duration_stats["长视频"] += 1

                            # 来源统计
                            source = video.get("chinese_source", "未知来源")
                            source_stats[source] = source_stats.get(source, 0) + 1

                        # 获取前3个推荐视频（按优先级排序：高>中>低）
                        top_recommendations = []

                        # 按优先级分组
                        high_priority = [v for v in unread_videos if v.get("chinese_priority") == "💖高"]
                        medium_priority = [v for v in unread_videos if v.get("chinese_priority") == "😜中"]
                        low_priority = [v for v in unread_videos if v.get("chinese_priority") == "👾低"]

                        # 按优先级依次选择，每个优先级内随机选择
                        selected_videos = []
                        for priority_group in [high_priority, medium_priority, low_priority]:
                            if len(selected_videos) >= 3:
                                break

                            # 从当前优先级组中随机选择，直到达到3个或该组用完
                            available = [v for v in priority_group if v not in selected_videos]
                            while available and len(selected_videos) < 3:
                                selected = random.choice(available)
                                selected_videos.append(selected)
                                available.remove(selected)

                        # 格式化推荐视频（字段内容中文）
                        for video in selected_videos:
                            top_recommendations.append({
                                "标题": video.get("title", "无标题视频"),
                                "链接": video.get("url", ""),
                                "页面ID": video.get("pageid", ""),
                                "时长": video.get("duration_str", ""),
                                "优先级": video.get("chinese_priority", ""),
                                "来源": video.get("chinese_source", "")
                            })

                        total_count = len(unread_videos)
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

    @safe_execute("获取运营数据失败")
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

    @safe_execute("创建日报卡片失败")
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