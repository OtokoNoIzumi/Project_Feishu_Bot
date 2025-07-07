"""
调度器服务模块（重构版）

该模块提供定时任务调度功能，专注于：
1. 任务调度管理
2. 时间触发机制
3. 事件发布机制（解耦前端）

设计原则：
- 完全独立于前端实现
- 通过事件机制通知其他组件
- 可被任意前端或API调用
"""

import time
import datetime
import schedule
import requests
import json
import os
from typing import Dict, Callable, List, Optional, Any, Set
from pathlib import Path

from Module.Common.scripts.common import debug_utils
from ..service_decorators import service_operation_safe, scheduler_operation_safe, external_api_safe, config_operation_safe
from Module.Services.constants import ServiceNames, SchedulerTaskTypes, SchedulerConstKeys
from Module.Services.message_aggregation_service import MessagePriority

class TaskUtils:
    """任务相关工具函数"""

    @staticmethod
    def get_task_function(scheduler_service, task_type: str) -> Optional[Callable]:
        """
        根据任务类型获取对应的触发函数

        Args:
            scheduler_service: 调度器服务实例
            task_type: 任务类型

        Returns:
            Optional[Callable]: 触发函数，如果找不到返回None
        """
        task_functions = {
            SchedulerTaskTypes.DAILY_SCHEDULE: scheduler_service.trigger_daily_schedule_reminder,
            SchedulerTaskTypes.BILI_UPDATES: scheduler_service.trigger_bilibili_updates_reminder,
            SchedulerTaskTypes.PERSONAL_STATUS_EVAL: scheduler_service.trigger_personal_status_evaluation,
            SchedulerTaskTypes.WEEKLY_REVIEW: scheduler_service.trigger_weekly_review,
            SchedulerTaskTypes.MONTHLY_REVIEW: scheduler_service.trigger_monthly_review,
        }
        return task_functions.get(task_type)


class ScheduledEvent:
    """定时任务事件"""
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.datetime.now()


class SchedulerService:
    """调度器服务（重构版）- 完全解耦的独立服务"""

    def __init__(self, app_controller=None):
        """
        初始化调度器服务

        Args:
            app_controller: 应用控制器实例
        """
        self.app_controller = app_controller
        self.scheduler = schedule
        self.tasks = {}  # 任务字典 {任务名: 任务对象}
        self.scheduled_functions = {}  # 已注册的定时任务函数
        self.event_listeners: Set[Callable] = set()  # 事件监听器



    def add_event_listener(self, listener: Callable):
        """添加事件监听器"""
        self.event_listeners.add(listener)

    def remove_event_listener(self, listener: Callable):
        """移除事件监听器"""
        self.event_listeners.discard(listener)

    @service_operation_safe("事件发布失败")
    def _publish_event(self, event: ScheduledEvent):
        """发布事件到所有监听器"""
        for listener in self.event_listeners:
            listener(event)

    @scheduler_operation_safe("添加每日任务失败", return_value=False)
    def add_daily_task(self, task_name: str, time_str: str, task_func: Callable, *args, **kwargs) -> bool:
        """
        添加每日定时任务

        Args:
            task_name: 任务名称
            time_str: 时间字符串，格式为"HH:MM"
            task_func: 任务函数
            *args: 传递给任务函数的位置参数
            **kwargs: 传递给任务函数的关键字参数

        Returns:
            bool: 是否添加成功
        """
        # 创建一个包装函数来传递参数
        def task_wrapper():
            return task_func(*args, **kwargs)

        # 添加任务
        job = self.scheduler.every().day.at(time_str).do(task_wrapper)
        self.tasks[task_name] = job
        self.scheduled_functions[task_name] = {
            'function': task_func,
            'time': time_str,
            'args': args,
            'kwargs': kwargs
        }

        return True

    @scheduler_operation_safe("添加每周任务失败", return_value=False)
    def add_weekly_task(self, task_name: str, day_of_week: str, time_str: str, task_func: Callable, *args, **kwargs) -> bool:
        """
        添加每周定时任务

        Args:
            task_name: 任务名称
            day_of_week: 星期几 (e.g., "monday", "sunday")
            time_str: 时间字符串 "HH:MM"
            task_func: 任务函数
            *args: 传递给任务函数的位置参数
            **kwargs: 传递给任务函数的关键字参数

        Returns:
            bool: 是否添加成功
        """
        def task_wrapper():
            return task_func(*args, **kwargs)

        # map day string to schedule method
        schedule_day = getattr(self.scheduler.every(), day_of_week, None)
        if not schedule_day:
            debug_utils.log_and_print(f"❌ 无效的星期: {day_of_week}", log_level="ERROR")
            return False

        job = schedule_day.at(time_str).do(task_wrapper)
        self.tasks[task_name] = job
        self.scheduled_functions[task_name] = {
            'function': task_func,
            'day_of_week': day_of_week,
            'time': time_str,
            'args': args,
            'kwargs': kwargs
        }
        return True

    @scheduler_operation_safe("添加间隔任务失败", return_value=False)
    def add_interval_task(self, task_name: str, interval_hours: int, start_offset_minutes: int, task_func: Callable, *args, **kwargs) -> bool:
        """
        添加固定间隔任务，在一天中的固定时间点触发
        e.g., 每12小时，偏移5分钟，只在 00:05, 12:05 触发

        Args:
            task_name: 任务名称
            interval_hours: 间隔小时数
            start_offset_minutes: 启动偏移分钟数
            task_func: 任务函数
            *args: 位置参数
            **kwargs: 关键字参数
        """
        # 先清理同名旧任务，避免重复
        if task_name in self.tasks:
            self.remove_task(task_name)

        # 创建任务包装函数
        def task_wrapper():
            task_func(*args, **kwargs)

        # 计算所有可能的触发时间点
        trigger_times = []
        for i in range(24 // interval_hours):
            hour = i * interval_hours
            time_str = f"{hour:02d}:{start_offset_minutes:02d}"
            trigger_times.append(time_str)

        # 为每个时间点创建每日任务
        jobs = []
        for time_str in trigger_times:
            job = self.scheduler.every().day.at(time_str).do(task_wrapper).tag(task_name)
            jobs.append(job)

        # 存储第一个job作为代表（用于管理）
        self.tasks[task_name] = jobs[0] if jobs else None

        self.scheduled_functions[task_name] = {
            'function': task_func,
            'interval_hours': interval_hours,
            'start_offset_minutes': start_offset_minutes,
            'trigger_times': trigger_times,
            'jobs_count': len(jobs),
            'args': args,
            'kwargs': kwargs
        }

        debug_utils.log_and_print(f"✅ 间隔任务已添加: {task_name} (触发时间: {', '.join(trigger_times)})", log_level="INFO")
        return True

    def remove_task(self, task_name: str) -> bool:
        """
        移除任务

        Args:
            task_name: 任务名称

        Returns:
            bool: 是否移除成功
        """
        if task_name in self.tasks:
            # 使用tag删除所有相关任务（适用于interval任务的多个job）
            self.scheduler.clear(tag=task_name)
            del self.tasks[task_name]
            if task_name in self.scheduled_functions:
                del self.scheduled_functions[task_name]
            return True
        debug_utils.log_and_print(f"任务 '{task_name}' 不存在", log_level="WARNING")
        return False

    def list_tasks(self) -> List[Dict]:
        """
        列出所有任务

        Returns:
            List[Dict]: 任务列表
        """
        task_list = []
        for name, job in self.tasks.items():
            task_info = {
                "name": name,
                "next_run": job.next_run,
                "last_run": getattr(job, 'last_run', None)
            }

            # 添加任务配置信息
            if name in self.scheduled_functions:
                func_info = self.scheduled_functions[name]
                task_info.update({
                    "time": func_info.get('time'),
                    "interval": func_info.get('interval'),
                    "function_name": func_info['function'].__name__
                })

            task_list.append(task_info)

        return task_list

    def run_pending(self) -> None:
        """执行待处理的任务"""
        self.scheduler.run_pending()

    def clear_all_tasks(self) -> None:
        """清除所有任务"""

        self.scheduler.clear()
        self.tasks = {}
        self.scheduled_functions = {}

    def get_status(self) -> Dict[str, Any]:
        """
        获取调度器服务状态

        Returns:
            Dict[str, Any]: 服务状态信息
        """
        return {
            "service_name": "scheduler",
            "status": "healthy",
            "task_count": len(self.tasks),
            "pending_jobs": len([job for job in self.scheduler.jobs if job.should_run]),
            "next_run": min([job.next_run for job in self.scheduler.jobs]) if self.scheduler.jobs else None,
            "tasks": self.list_tasks(),
            "event_listeners": len(self.event_listeners),
            "details": {
                "scheduler_active": True,
                "total_tasks": len(self.tasks),
                "scheduled_functions": list(self.scheduled_functions.keys())
            }
        }

    # ================ 服务状态检测方法 ================

    def check_services_status(self) -> Dict[str, Any]:
        """
        检测服务状态

        Returns:
            Dict[str, Any]: 服务状态信息
        """
        services_status = {
            "check_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "services": {}
        }

        # 获取配置服务
        config_service = self.app_controller.get_service(ServiceNames.CONFIG) if self.app_controller else None

        # 检查B站API服务
        services_status["services"]["bilibili_api"] = self._check_bilibili_api_status(config_service)

        # 检查gradio服务
        services_status["services"]["gradio"] = self._check_gradio_service_status(config_service)

        return services_status

    @external_api_safe("B站API状态检查失败", return_value={"service_name": "B站API服务", "status": "error", "message": "检查失败"}, api_name="Bilibili")
    def _check_bilibili_api_status(self, config_service) -> Dict[str, Any]:
        """
        检查B站API服务状态

        Args:
            config_service: 配置服务实例

        Returns:
            Dict[str, Any]: B站API状态信息
        """
        status_info = {
            "service_name": "B站API服务",
            "status": "unknown",
            "message": "",
            "url": "",
            "response_time": None,
            "enabled": False
        }

        # 获取API基础URL
        api_base = os.getenv("BILI_API_BASE", "https://localhost:3000")
        verify_ssl = os.getenv("BILI_API_VERIFY_SSL", "true").lower() != "false"
        if not api_base or api_base == "https://localhost:3000":
            status_info.update({
                "status": "disabled",
                "message": "B站API服务未配置或使用默认配置",
                "enabled": False
            })
            return status_info

        status_info["enabled"] = True
        status_info["url"] = api_base

        # 发送健康检查请求
        start_time = time.time()
        response = requests.get(
            api_base,
            timeout=10,
            verify=verify_ssl
        )
        response_time = round((time.time() - start_time) * 1000, 2)  # 毫秒

        status_info["response_time"] = f"{response_time}ms"

        if response.status_code == 200:
            try:
                resp_data = response.json()
                if "BiliTools API Service is running" in resp_data.get("message", ""):
                    status_info.update({
                        "status": "healthy",
                        "message": "服务运行正常"
                    })
                else:
                    status_info.update({
                        "status": "warning",
                        "message": f"服务响应异常: {resp_data.get('message', '未知响应')}"
                    })
            except:
                status_info.update({
                    "status": "warning",
                    "message": "服务响应格式异常"
                })
        else:
            status_info.update({
                "status": "error",
                "message": f"HTTP状态码: {response.status_code}"
            })

        return status_info

    @external_api_safe("Gradio服务状态检查失败", return_value={"service_name": "Gradio图像服务", "status": "error", "message": "检查失败"}, api_name="Gradio")
    def _check_gradio_service_status(self, config_service) -> Dict[str, Any]:
        """
        检查gradio服务状态

        Args:
            config_service: 配置服务实例

        Returns:
            Dict[str, Any]: gradio服务状态信息
        """
        status_info = {
            "service_name": "Gradio图像服务",
            "status": "unknown",
            "message": "",
            "url": "",
            "response_time": None,
            "enabled": False,
            "token_info": {}
        }

        # 获取SERVER_ID配置
        server_id = ""
        if config_service:
            try:
                server_id = config_service.get("SERVER_ID", "")
            except:
                server_id = ""

        if not server_id:
            server_id = os.getenv("SERVER_ID", "")

        if not server_id:
            status_info.update({
                "status": "disabled",
                "message": "SERVER_ID未配置，图像服务不可用",
                "enabled": False
            })
            return status_info

        status_info["enabled"] = True
        gradio_url = f"https://{server_id}"
        status_info["url"] = gradio_url

        # 检查gradio服务连接
        from gradio_client import Client
        import contextlib
        import io

        start_time = time.time()

        # 抑制gradio_client的输出
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            client = Client(gradio_url)
            response_time = round((time.time() - start_time) * 1000, 2)

            status_info["response_time"] = f"{response_time}ms"

            # 尝试简单连接验证而不获取详细API信息
            try:
                # 只检查客户端是否成功创建，不调用view_api()
                if hasattr(client, 'endpoints') or hasattr(client, 'app'):
                    status_info.update({
                        "status": "healthy",
                        "message": "服务连接正常"
                    })
                else:
                    status_info.update({
                        "status": "warning",
                        "message": "服务连接异常"
                    })

                # 检查token信息（如果可用）
                # 使用图像服务的原生API获取令牌信息
                image_service = None
                if self.app_controller:
                    image_service = self.app_controller.get_service('image')
                status_info["token_info"] = self._get_gradio_token_info(image_service)

            except Exception as api_error:
                status_info.update({
                    "status": "warning",
                    "message": f"服务验证异常: {str(api_error)}"
                })

        return status_info

    @external_api_safe("获取Gradio令牌信息失败", return_value={"has_token": False, "status": "error"}, api_name="Gradio")
    def _get_gradio_token_info(self, image_service) -> Dict[str, Any]:
        """
        获取gradio令牌信息（通过图像服务的原生API）

        Args:
            image_service: 图像服务实例

        Returns:
            Dict[str, Any]: 令牌信息
        """
        token_info = {
            "has_token": False,
            "expires_at": None,
            "expires_in_hours": None,
            "status": "unknown"
        }

        if not image_service:
            return token_info

        # 调用图像服务的认证状态API
        auth_status = image_service.get_auth_status()

        if "error" in auth_status:
            token_info["status"] = "error"
            return token_info

        # 从API结果中提取信息
        has_cookies = auth_status.get("has_cookies", False)
        has_auth_token = auth_status.get("has_auth_token", False)
        is_expired = auth_status.get("is_expired", True)
        hours_remaining = auth_status.get("hours_remaining", 0)
        expires_at = auth_status.get("expires_at", "")

        token_info.update({
            "has_token": has_cookies or has_auth_token,
            "expires_at": expires_at,
            "expires_in_hours": round(hours_remaining, 1),
            "status": "valid" if not is_expired else "expired"
        })

        return token_info

    # ================ 定时任务执行方法 ================

    @scheduler_operation_safe("每日日程提醒任务失败")
    def trigger_daily_schedule_reminder(self) -> None:
        """
        触发每日日程提醒
        独立执行：发布事件给MessageProcessor处理

        注意：数据构建逻辑已移至MessageProcessor，这里只负责事件触发
        """
        # 获取管理员ID
        admin_id = self._get_admin_id()
        if not admin_id:
            return

        # 检查服务状态
        services_status = self.check_services_status()

        # 发布轻量级事件，数据生成交给MessageProcessor
        event = ScheduledEvent("daily_schedule_reminder", {
            SchedulerConstKeys.ADMIN_ID: admin_id,
            SchedulerConstKeys.SCHEDULER_TYPE: SchedulerTaskTypes.DAILY_SCHEDULE,
            "services_status": services_status  # 添加服务状态信息
        })

        self._publish_event(event)

    @scheduler_operation_safe("B站更新提醒任务失败")
    def trigger_bilibili_updates_reminder(self, sources: Optional[List[str]] = None) -> None:
        """
        触发B站更新提醒
        独立执行：调用B站API → 发布事件

        Args:
            sources: 可选的源列表，如 ["favorites", "dynamic"]
        """
        # 检查是否为夜间静默时间（23:00-07:00）
        current_hour = datetime.datetime.now().hour
        is_night_silent = current_hour >= 23 or current_hour < 7

        # 获取夜间静默配置（默认开启）
        night_silent_enabled = True
        if self.app_controller:
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            if config_service:
                try:
                    night_silent_enabled = config_service.get_env("BILI_NIGHT_SILENT", "true").lower() == "true"
                except:
                    night_silent_enabled = True

        # 获取管理员ID
        admin_id = self._get_admin_id()
        if not admin_id:
            return

        # 调用B站API处理数据源
        api_result = self._call_bilibili_api(sources)
        if not api_result['success']:
            debug_utils.log_and_print("B站API调用失败，跳过本次更新提醒", log_level="WARNING")
            return

        debug_utils.log_and_print(f"B站更新提醒任务执行，sources: {sources}", log_level="INFO")
        # 判断是否需要静默处理
        if is_night_silent and night_silent_enabled:
            return  # 静默模式：只处理API，不发送事件

        # 发布事件（非静默时间）
        event = ScheduledEvent("bilibili_updates_reminder", {
            SchedulerConstKeys.ADMIN_ID: admin_id,
            "sources": sources,
            "api_result": api_result,
            SchedulerConstKeys.SCHEDULER_TYPE: SchedulerTaskTypes.BILI_UPDATES
        })

        self._publish_event(event)

    @scheduler_operation_safe("个人状态评估任务失败")
    def trigger_personal_status_evaluation(self, user_id: str):
        """触发个人状态评估任务"""
        debug_utils.log_and_print("个人状态评估任务执行", log_level="INFO")

        # 简化测试数据
        data = {
            "task_type": "个人状态评估",
            "execution_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "user_id": user_id,
            "status": "测试执行成功"
        }

        # 将数据发送到信息汇总服务
        message_aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
        if message_aggregation_service:
            message_aggregation_service.add_message(
                source_type="personal_status_eval",
                content=data,
                user_id=user_id,
                priority=MessagePriority.NORMAL
            )

    @scheduler_operation_safe("周度盘点任务失败")
    def trigger_weekly_review(self, user_id: str):
        """触发周度盘点任务"""
        debug_utils.log_and_print("周度盘点任务执行", log_level="INFO")

        # 简化测试数据
        data = {
            "task_type": "周度盘点",
            "execution_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "user_id": user_id,
            "week": f"第{datetime.datetime.now().strftime('%W')}周",
            "status": "测试执行成功"
        }

        message_aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
        if message_aggregation_service:
            message_aggregation_service.add_message(
                source_type="weekly_review",
                content=data,
                user_id=user_id,
                priority=MessagePriority.HIGH
            )

    @scheduler_operation_safe("月度盘点任务失败")
    def trigger_monthly_review(self, user_id: str):
        """触发月度盘点任务"""
        debug_utils.log_and_print("月度盘点任务执行", log_level="INFO")

        # 简化测试数据
        data = {
            "task_type": "月度盘点",
            "execution_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "user_id": user_id,
            "month": datetime.datetime.now().strftime("%Y年%m月"),
            "status": "测试执行成功"
        }

        message_aggregation_service = self.app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
        if message_aggregation_service:
            message_aggregation_service.add_message(
                source_type="monthly_review",
                content=data,
                user_id=user_id,
                priority=MessagePriority.HIGH
            )

    # ================ 数据收集方法 ================

    @service_operation_safe("个人状态数据收集失败", return_value={})
    def _collect_personal_status(self) -> Dict[str, Any]:
        """收集个人状态数据"""
        status_data = {}
        try:
            if self.app_controller:
                health = self.app_controller.health_check()
                status_data['system_status'] = health.get('overall_status', 'unknown')
                status_data['healthy_services_ratio'] = f"{health['summary']['healthy']}/{health['summary']['total']}"

                pending_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)
                if pending_service:
                    stats = pending_service.get_cache_statistics()
                    status_data['pending_operations'] = stats.get('total_operations', 0)
        except Exception as e:
            debug_utils.log_and_print(f"收集个人状态数据异常: {e}", log_level="ERROR")
            status_data["error"] = str(e)
        return status_data

    @service_operation_safe("周度数据收集失败", return_value={})
    def _collect_weekly_review_data(self, user_id: str) -> Dict[str, Any]:
        """收集周度盘点数据"""
        return {
            "title": f"第{datetime.datetime.now().strftime('%W')}周回顾",
            "summary": "系统稳定运行，所有定时任务按计划执行。",
            "highlights": [
                "信息汇总服务上线并稳定运行",
                "处理了X个B站视频更新",
                "完成了Y个用户交互操作"
            ]
        }

    @service_operation_safe("月度数据收集失败", return_value={})
    def _collect_monthly_review_data(self, user_id: str) -> Dict[str, Any]:
        """收集月度盘点数据"""
        return {
            "title": f"{datetime.datetime.now().strftime('%Y年%m月')}回顾",
            "summary": "本月系统表现出色，无重大故障。",
            "achievements": [
                "新定时任务架构（个人评估、周/月度盘点）成功部署",
                "AI信息汇总功能提升了信息处理效率",
            ],
            "next_month_goals": ["引入更智能的调度策略", "优化LLM调用成本"]
        }

    # ================ 独立API方法 ================

    @external_api_safe("B站更新检查失败", return_value={"success": False, "error": "检查失败"}, api_name="Bilibili")
    def trigger_bilibili_update_check(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """触发B站更新检查的独立API"""
        result = self._call_bilibili_api(sources)
        return result

    # ================ 私有辅助方法 ================

    @config_operation_safe("获取管理员ID失败", return_value=None)
    def _get_admin_id(self) -> Optional[str]:
        """
        获取管理员ID，优先级：环境变量 > 静态配置
        """
        config_service = self.app_controller.get_service(ServiceNames.CONFIG) if self.app_controller else None
        if not config_service:
            debug_utils.log_and_print("配置服务不可用，无法获取管理员ID", log_level="WARNING")
            return None

        # 优先从环境变量获取，其次静态配置，最后返回None
        admin_id = config_service.get("ADMIN_ID", None)
        if not admin_id:
            debug_utils.log_and_print("未配置ADMIN_ID，无法发送定时提醒", log_level="WARNING")
            return None

        return admin_id

    @external_api_safe("B站API调用失败", return_value={"success": False, "error": "API调用失败"}, api_name="Bilibili")
    def _call_bilibili_api(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        调用B站API处理数据源

        Args:
            sources: 可选的源列表

        Returns:
            Dict[str, Any]: API调用结果
        """
        # 从环境变量获取API配置
        api_base = os.getenv("BILI_API_BASE", "https://localhost:3000")
        verify_ssl = os.getenv("BILI_API_VERIFY_SSL", "True").lower() != "false"

        url = f"{api_base}/api/admin/process_sources"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "admin_secret_key": "izumi_the_beauty",
            "debug_mode": True,
            "skip_deduplication": False,
            "fav_list_id": 1397395905,
            "delete_after_process": True,
            "dynamic_hours_ago": 24,
            "dynamic_max_videos": 50,
            "homepage_max_videos": 20,
            "blocked_up_list": None,
        }

        if sources is not None:
            data["sources"] = sources

        # 发送API请求（增加超时设置，适应B站API的长时间处理）
        # 连接超时10秒，读取超时300秒（5分钟），适应B站数据处理的时间需求
        # timeout_settings = (10, 300)  # (connect_timeout, read_timeout)

        # 禁用代理，避免代理服务器的超时限制
        # proxies = {
        #     'http': None,
        #     'https': None
        # }

        # debug_utils.log_and_print("B站API调用：已禁用代理，直连服务器", log_level="DEBUG")

        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(data),
            verify=verify_ssl,
            # timeout=timeout_settings,
            # proxies=proxies
        )

        if not verify_ssl:
            debug_utils.log_and_print("警告：SSL证书验证已禁用", log_level="WARNING")

        try:
            resp_json = response.json()

            # 返回完整的API结果
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": resp_json,
                "sources": sources
            }

        except Exception as e:
            debug_utils.log_and_print(f"B站API响应解析失败: {e}", log_level="WARNING")
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": {"message": "响应解析失败"},
                "sources": sources
            }
