"""
异步非阻塞限流器（原子能力）

用于控制 API 调用频率（RPM：每分钟请求数）
"""

import asyncio
import time
from typing import List


class AsyncRateLimiter:
    """
    异步非阻塞限流器

    用于限制在指定时间窗口内的请求数量
    """

    def __init__(self, max_count: int, time_limit: int = 60):
        """
        Args:
            max_count: 时间窗口内允许的最大请求数
            time_limit: 时间窗口长度（秒），默认 60 秒（1 分钟）
        """
        self.max_count = max_count
        self.time_limit = time_limit
        self.timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def check_and_wait(self):
        """
        检查并异步等待（Non-blocking wait）

        如果当前请求数已达到上限，会异步等待直到可以继续
        """
        async with self._lock:
            now = time.time()
            # 移除窗口外的时间戳
            self.timestamps = [t for t in self.timestamps if now - t < self.time_limit]

            if len(self.timestamps) >= self.max_count:
                # 计算需等待时间
                wait_time = self.time_limit - (now - self.timestamps[0])
                if wait_time > 0:
                    # 释放锁，异步等待
                    await asyncio.sleep(wait_time)

                    # 等待结束，重新校准
                    now = time.time()
                    self.timestamps = [
                        t for t in self.timestamps if now - t < self.time_limit
                    ]

            self.timestamps.append(now)
