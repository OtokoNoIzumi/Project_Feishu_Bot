"""临时信息数据处理模块

负责临时信息相关的数据获取和处理
包括订阅服务用量监控等临时业务功能
"""

import requests
import base64
import re
from typing import Dict, Any
from datetime import datetime, timedelta
from Module.Common.scripts.common import debug_utils


class SubscriptionUsageData:
    """订阅服务用量数据处理器"""

    def __init__(self, app_controller):
        self.app_controller = app_controller

    def get_subscription_usage_data(self, _data_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取订阅服务用量数据"""
        try:
            # 从环境变量获取订阅链接和总流量
            config_service = self.app_controller.get_service("config")
            url = config_service.get_env("SUBSCRIPTION_URL")
            total_gb_str = config_service.get_env("SUBSCRIPTION_TOTAL_GB")

            if not url:
                return {
                    "success": False,
                    "error": "未配置SUBSCRIPTION_URL环境变量"
                }

            if not total_gb_str:
                return {
                    "success": False,
                    "error": "未配置SUBSCRIPTION_TOTAL_GB环境变量"
                }

            try:
                total_gb = int(total_gb_str)
            except ValueError:
                return {
                    "success": False,
                    "error": "SUBSCRIPTION_TOTAL_GB环境变量必须是数字"
                }

            # 获取订阅内容
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # 解码BASE64内容
            b64_content = response.text.strip()
            decoded_content = base64.b64decode(b64_content).decode('utf-8')
            content_list = decoded_content.split('\n')
            formatted_content = [content.split("#") for content in content_list]

            # 提取剩余流量
            traffic_gb = self._extract_traffic_value(formatted_content)

            if traffic_gb is None:
                return {
                    "success": False,
                    "error": "未能在订阅内容中找到剩余流量信息"
                }

            # 计算用量分析
            days_left = self._get_days_left_in_month()
            days_in_month = self._get_days_in_month()
            daily_available = traffic_gb / days_left
            avg_benchmark_per_day = total_gb / days_in_month
            benchmark_percentage = (daily_available / avg_benchmark_per_day) * 100
            used_gb = total_gb - traffic_gb

            return {
                "success": True,
                "data": {
                    "remaining_traffic_gb": traffic_gb,
                    "used_gb": used_gb,
                    "total_gb": total_gb,
                    "days_left_in_month": days_left,
                    "days_in_month": days_in_month,
                    "daily_available_gb": daily_available,
                    "avg_benchmark_per_day": avg_benchmark_per_day,
                    "benchmark_percentage": benchmark_percentage,
                }
            }

        except Exception as e:
            debug_utils.log_and_print(f"获取订阅用量数据失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"获取订阅用量数据失败: {str(e)}"
            }

    def _extract_traffic_value(self, formatted_content: list) -> float:
        """从订阅内容中提取流量数值"""
        for item in formatted_content:
            for part in item:
                if "剩余流量" in part:
                    match = re.search(r"剩余流量[:：]?\s*([\d.]+)\s*(GB|G|MB|M|TB|T)?", part, re.IGNORECASE)
                    if match:
                        value = float(match.group(1))
                        unit = match.group(2) or "GB"
                        unit = unit.upper()
                        if unit in ["GB", "G"]:
                            return value
                        elif unit in ["MB", "M"]:
                            return value / 1024
                        elif unit in ["TB", "T"]:
                            return value * 1024
        return None

    def _get_days_left_in_month(self) -> int:
        """获取本月剩余天数"""
        today = datetime.now()
        next_month = today.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        return (last_day - today).days + 1

    def _get_days_in_month(self) -> int:
        """获取本月总天数"""
        today = datetime.now()
        next_month = today.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        return last_day.day

