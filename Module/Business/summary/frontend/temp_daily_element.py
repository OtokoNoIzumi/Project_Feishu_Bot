"""临时信息卡片构建模块

负责临时信息相关的前端卡片构建和展示逻辑
包括订阅服务用量监控等临时业务功能的前端展示
"""

from typing import Dict, Any, List
from Module.Adapters.feishu.cards.json_builder import JsonBuilder


class SubscriptionUsageElement:
    """订阅服务用量卡片元素构建器"""

    def build_subscription_usage_elements(
        self, usage_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建订阅服务用量元素"""
        elements = []
        content = self.format_subscription_usage(usage_data)
        elements.append(JsonBuilder.build_markdown_element(content))
        return elements

    def format_subscription_usage(self, usage_data: Dict[str, Any]) -> str:
        """格式化订阅服务用量信息"""
        content = "\n\n📊 **订阅服务用量监控**"

        if not usage_data.get("success", False):
            error_msg = usage_data.get("error", "未知错误")
            content += f"\n❌ **获取失败:** {error_msg}"
            return content

        data = usage_data.get("data", {})

        # 基础用量信息
        remaining_traffic = data.get("remaining_traffic_gb", 0)
        used_gb = data.get("used_gb", 0)
        total_gb = data.get("total_gb", 100)
        daily_available = data.get("daily_available_gb", 0)
        avg_benchmark_per_day = data.get("avg_benchmark_per_day", 0)
        benchmark_percentage = data.get("benchmark_percentage", 0)
        days_left_in_month = data.get("days_left_in_month", 0)

        content += f"\n📈 **剩余流量:** {remaining_traffic:.2f} GB"
        content += f"\n⚡ **日均可用:** {daily_available:.2f} GB"

        # 生成使用建议
        suggestion_text = self._generate_usage_suggestion(
            daily_available, avg_benchmark_per_day, benchmark_percentage,
            used_gb, total_gb, days_left_in_month
        )
        content += f"\n{suggestion_text}"


        return content

    def _generate_usage_suggestion(self, daily_available: float, avg_benchmark_per_day: float, benchmark_percentage: float,
                                  used_gb: float, total_gb: float, days_left_in_month: int) -> str:
        """生成使用建议文本"""
        # 预计当月总用量（粗略估算）
        projected_monthly_usage = daily_available * 30

        # 是否需要考虑追加套餐的前提条件（流量偏紧时才建议）
        usage_percent = (used_gb / total_gb) * 100
        should_suggest_package = (usage_percent >= 90) or (days_left_in_month <= 20)

        if daily_available >= avg_benchmark_per_day:
            # 流量宽裕
            surplus_ratio = (benchmark_percentage - 100) / 100
            if surplus_ratio >= 0.5:
                return f"✅ **使用建议:** 流量非常充裕（比{total_gb}GB的日均基准多{surplus_ratio*100:.0f}%），加油多多使用"
            else:
                return f"✅ **使用建议:** 流量充足（比{total_gb}GB的日均基准多{surplus_ratio*100:.0f}%），可适度放宽使用"

        else:
            # 流量偏紧
            shortage_ratio = (100 - benchmark_percentage) / 100
            if shortage_ratio >= 0.3:
                suggestion = f"🔴 **使用建议:** 流量紧张（只有{total_gb}GB的日均基准的{benchmark_percentage:.0f}%），请谨慎使用"
            else:
                suggestion = f"⚠️ **使用建议:** 流量略显不足（只有{total_gb}GB的日均基准的{shortage_ratio*100:.0f}%），建议适度节约"

            # 套餐追加提示（流量偏紧时才建议）
            if should_suggest_package and projected_monthly_usage > total_gb:
                if total_gb + 40 <= projected_monthly_usage <= total_gb + 50:
                    suggestion += f"\n💡 按当前趋势，本月可能达到约{total_gb + 40}–{total_gb + 50}GB，可考虑追加8元流量包"
                elif total_gb + 90 <= projected_monthly_usage <= total_gb + 100:
                    suggestion += f"\n💡 按当前趋势，本月可能接近{total_gb + 100}GB，建议追加15元流量包"

            return suggestion
