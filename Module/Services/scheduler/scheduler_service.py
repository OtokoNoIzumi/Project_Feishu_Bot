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

        debug_utils.log_and_print("SchedulerService 初始化成功", log_level="INFO")

    def add_event_listener(self, listener: Callable):
        """添加事件监听器"""
        self.event_listeners.add(listener)
        debug_utils.log_and_print(f"添加事件监听器: {listener.__name__}", log_level="DEBUG")

    def remove_event_listener(self, listener: Callable):
        """移除事件监听器"""
        self.event_listeners.discard(listener)
        debug_utils.log_and_print(f"移除事件监听器: {listener.__name__}", log_level="DEBUG")

    def _publish_event(self, event: ScheduledEvent):
        """发布事件到所有监听器"""
        debug_utils.log_and_print(f"发布事件: {event.event_type}", log_level="DEBUG")
        for listener in self.event_listeners:
            try:
                listener(event)
            except Exception as e:
                debug_utils.log_and_print(f"事件监听器 {listener.__name__} 处理失败: {e}", log_level="ERROR")

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
        try:
            # 创建一个包装函数来传递参数
            def task_wrapper():
                debug_utils.log_and_print(f"执行定时任务: {task_name}", log_level="INFO")
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

            debug_utils.log_and_print(f"定时任务 '{task_name}' 已添加，执行时间: {time_str}", log_level="INFO")
            return True
        except Exception as e:
            debug_utils.log_and_print(f"添加任务失败: {e}", log_level="ERROR")
            return False

    def add_interval_task(self, task_name: str, interval: int, task_func: Callable, *args, **kwargs) -> bool:
        """
        添加间隔定时任务

        Args:
            task_name: 任务名称
            interval: 间隔秒数
            task_func: 任务函数
            *args: 传递给任务函数的位置参数
            **kwargs: 传递给任务函数的关键字参数

        Returns:
            bool: 是否添加成功
        """
        try:
            # 创建一个包装函数来传递参数
            def task_wrapper():
                debug_utils.log_and_print(f"执行间隔任务: {task_name}", log_level="INFO")
                return task_func(*args, **kwargs)

            # 添加任务
            job = self.scheduler.every(interval).seconds.do(task_wrapper)
            self.tasks[task_name] = job
            self.scheduled_functions[task_name] = {
                'function': task_func,
                'interval': interval,
                'args': args,
                'kwargs': kwargs
            }

            debug_utils.log_and_print(f"间隔任务 '{task_name}' 已添加，间隔: {interval}秒", log_level="INFO")
            return True
        except Exception as e:
            debug_utils.log_and_print(f"添加间隔任务失败: {e}", log_level="ERROR")
            return False

    def remove_task(self, task_name: str) -> bool:
        """
        移除任务

        Args:
            task_name: 任务名称

        Returns:
            bool: 是否移除成功
        """
        if task_name in self.tasks:
            self.scheduler.cancel_job(self.tasks[task_name])
            del self.tasks[task_name]
            if task_name in self.scheduled_functions:
                del self.scheduled_functions[task_name]
            debug_utils.log_and_print(f"任务 '{task_name}' 已移除", log_level="INFO")
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
        debug_utils.log_and_print("清除所有定时任务", log_level="INFO")
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

    # ================ 定时任务执行方法 ================

    def trigger_daily_schedule_reminder(self) -> None:
        """
        触发每日日程提醒
        独立执行：发布事件给MessageProcessor处理

        注意：数据构建逻辑已移至MessageProcessor，这里只负责事件触发
        """
        try:
            debug_utils.log_and_print("开始执行每日日程提醒任务", log_level="INFO")

            # 获取管理员ID
            admin_id = self._get_admin_id()
            if not admin_id:
                return

            # 发布轻量级事件，数据生成交给MessageProcessor
            event = ScheduledEvent("daily_schedule_reminder", {
                "admin_id": admin_id,
                "message_type": "daily_schedule"
            })

            self._publish_event(event)
            debug_utils.log_and_print(f"✅ 日程提醒事件已发布", log_level="INFO")

        except Exception as e:
            debug_utils.log_and_print(f"执行每日日程提醒任务失败: {e}", log_level="ERROR")

    def trigger_bilibili_updates_reminder(self, sources: Optional[List[str]] = None) -> None:
        """
        触发B站更新提醒
        独立执行：调用B站API → 发布事件

        Args:
            sources: 可选的源列表，如 ["favorites", "dynamic"]
        """
        try:
            debug_utils.log_and_print(f"开始执行B站更新提醒任务，源: {sources or '默认'}", log_level="INFO")

            # 获取管理员ID
            admin_id = self._get_admin_id()
            if not admin_id:
                return

            # 调用B站API处理数据源
            api_result = self._call_bilibili_api(sources)
            if not api_result['success']:
                debug_utils.log_and_print("B站API调用失败，跳过本次更新提醒", log_level="WARNING")
                return

            # 发布事件
            event = ScheduledEvent("bilibili_updates_reminder", {
                "admin_id": admin_id,
                "sources": sources,
                "api_result": api_result,
                "message_type": "bilibili_updates"
            })

            self._publish_event(event)
            debug_utils.log_and_print(f"✅ B站更新提醒事件已发布", log_level="INFO")

        except Exception as e:
            debug_utils.log_and_print(f"执行B站更新提醒任务失败: {e}", log_level="ERROR")

    # ================ 独立API方法 ================

    def get_schedule_data(self) -> Dict[str, Any]:
        """
        获取日程数据的独立API

        注意：实际数据生成已移至MessageProcessor，这里返回提示信息
        """
        try:
            return {
                "message": "日程数据生成已移至MessageProcessor，请通过MessageProcessor.create_scheduled_message()获取",
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            debug_utils.log_and_print(f"获取日程数据失败: {e}", log_level="ERROR")
            return {"error": str(e)}

    def trigger_bilibili_update_check(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """触发B站更新检查的独立API"""
        try:
            result = self._call_bilibili_api(sources)
            debug_utils.log_and_print(f"B站更新检查完成: {result}", log_level="INFO")
            return result
        except Exception as e:
            debug_utils.log_and_print(f"B站更新检查失败: {e}", log_level="ERROR")
            return {"success": False, "error": str(e)}

    # ================ 私有辅助方法 ================

    def _get_admin_id(self) -> Optional[str]:
        """获取管理员ID"""
        try:
            config_service = self.app_controller.get_service('config') if self.app_controller else None
            if not config_service:
                debug_utils.log_and_print("配置服务不可用，无法获取管理员ID", log_level="WARNING")
                return None

            admin_id = ""
            try:
                admin_id = config_service.get_env("ADMIN_ID", "")
            except:
                admin_id = config_service.get("admin_id", "")

            if not admin_id:
                debug_utils.log_and_print("未配置ADMIN_ID，无法发送定时提醒", log_level="WARNING")
                return None

            return admin_id

        except Exception as e:
            debug_utils.log_and_print(f"获取管理员ID失败: {e}", log_level="ERROR")
            return None

    def _call_bilibili_api(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        调用B站API处理数据源

        Args:
            sources: 可选的源列表

        Returns:
            Dict[str, Any]: API调用结果
        """
        try:
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

            # 发送API请求
            response = requests.post(url, headers=headers, data=json.dumps(data), verify=verify_ssl)

            if not verify_ssl:
                debug_utils.log_and_print("警告：SSL证书验证已禁用", log_level="WARNING")

            debug_utils.log_and_print(f"B站API调用状态: {response.status_code}", log_level="INFO")

            try:
                resp_json = response.json()
                debug_utils.log_and_print(f"B站API响应: {json.dumps(resp_json, ensure_ascii=False)}", log_level="DEBUG")

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

        except Exception as e:
            debug_utils.log_and_print(f"B站API调用失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": str(e),
                "sources": sources
            }