"""
调度器服务模块

该模块提供定时任务调度功能
"""

import time
import datetime
import schedule
from typing import Dict, Callable, List


class SchedulerService:
    """调度器服务"""

    def __init__(self):
        """初始化调度器服务"""
        self.scheduler = schedule
        self.tasks = {}  # 任务字典 {任务名: 任务对象}

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
                return task_func(*args, **kwargs)

            # 添加任务
            job = self.scheduler.every().day.at(time_str).do(task_wrapper)
            self.tasks[task_name] = job
            return True
        except Exception as e:
            print(f"添加任务失败: {e}")
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
                return task_func(*args, **kwargs)

            # 添加任务
            job = self.scheduler.every(interval).seconds.do(task_wrapper)
            self.tasks[task_name] = job
            return True
        except Exception as e:
            print(f"添加任务失败: {e}")
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
            return True
        return False

    def list_tasks(self) -> List[Dict]:
        """
        列出所有任务

        Returns:
            List[Dict]: 任务列表
        """
        return [{"name": name, "next_run": job.next_run} for name, job in self.tasks.items()]

    def run_pending(self) -> None:
        """执行待处理的任务"""
        self.scheduler.run_pending()

    def clear_all_tasks(self) -> None:
        """清除所有任务"""
        self.scheduler.clear()
        self.tasks = {}