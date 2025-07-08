"""
B站广告跳过服务

统一处理B站相关的外部API交互，包括：
1. 运营数据API调用
2. B站链接转换工具
3. 广告跳过相关功能
"""

import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import DefaultValues, EnvVars
from Module.Services.service_decorators import service_operation_safe


class BiliAdskipService:
    """
    B站广告跳过服务

    负责处理所有与B站相关的外部API交互和工具功能
    """

    def __init__(self, app_controller=None):
        """初始化B站广告跳过服务"""
        self.app_controller = app_controller
        self._load_config()

    def _load_config(self):
        """加载配置"""
        # 统一默认值
        self.bili_api_base_url = DefaultValues.DEFAULT_BILI_API_BASE
        self.bili_admin_secret = DefaultValues.DEFAULT_ADMIN_SECRET

        if not self.app_controller:
            return

        config_service = self.app_controller.get_service('config')
        if not config_service:
            return

        # 获取B站API配置
        self.bili_api_base_url = config_service.get_env(EnvVars.BILI_API_BASE, self.bili_api_base_url)
        self.bili_admin_secret = config_service.get_env(EnvVars.ADMIN_SECRET_KEY, self.bili_admin_secret)

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.is_api_available()

    def is_api_available(self) -> bool:
        """检查B站API是否可用"""
        return (self.bili_api_base_url and
                self.bili_api_base_url != DefaultValues.DEFAULT_BILI_API_BASE)

    @service_operation_safe("获取运营数据失败")
    def get_operation_data(self) -> Optional[Dict[str, Any]]:
        """
        获取运营数据（每日必须，周一还要获取周数据）

        Returns:
            Optional[Dict[str, Any]]: 运营数据，包含daily数据，周一还包含weekly数据
        """
        now = datetime.now()
        today_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        is_monday = now.weekday() == 0  # 0是周一

        # 检查B站API是否可用
        if not self.is_api_available():
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


def convert_to_bili_app_link(web_url: str) -> str:
    """
    将B站网页链接转换为移动端APP链接

    这是一个纯工具函数，不依赖任何外部服务或状态

    Args:
        web_url: B站网页链接

    Returns:
        str: 转换后的APP链接
    """
    if not web_url:
        return web_url

    try:
        # 提取BV号
        if "bilibili.com/video/" in web_url:
            # 处理标准的视频链接
            if "/video/BV" in web_url:
                bv_start = web_url.find("/video/BV") + 7
                bv_end = web_url.find("?", bv_start)
                if bv_end == -1:
                    bv_end = web_url.find("/", bv_start)
                if bv_end == -1:
                    bv_end = len(web_url)

                bv_id = web_url[bv_start:bv_end]
                if bv_id.startswith("BV"):
                    # 构建APP链接
                    app_url = f"bilibili://video/{bv_id}"
                    return app_url

        return web_url

    except Exception as e:
        debug_utils.log_and_print(f"❌ 链接转换失败: {e}", log_level="WARNING")
        return web_url
