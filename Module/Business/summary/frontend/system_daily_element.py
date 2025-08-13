"""系统状态卡片构建模块

负责系统状态相关的前端卡片构建和展示逻辑
"""

from typing import Dict, Any, List
from datetime import datetime
from Module.Adapters.feishu.cards.json_builder import JsonBuilder


class SystemDailyElement:
    """系统状态卡片元素构建器"""

    # region 运营数据
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

    # region 服务状态

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
