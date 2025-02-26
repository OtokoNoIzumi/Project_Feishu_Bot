"""
缓存服务模块

该模块提供缓存管理功能，包括用户信息缓存和事件缓存
"""

import os
import json
import time
from typing import Dict, Any, Optional


class CacheService:
    """缓存管理服务"""

    def __init__(self, cache_dir: str = "cache"):
        """
        初始化缓存服务

        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        self.user_cache_file = os.path.join(cache_dir, "user_cache.json")
        self.event_cache_file = os.path.join(cache_dir, "processed_events.json")

        # 用户缓存结构：{open_id: {"name": str, "timestamp": float}}
        self.user_cache: Dict[str, Dict] = self._load_user_cache()

        # 事件缓存结构：{event_id: timestamp}
        self.event_cache: Dict[str, float] = self._load_event_cache()

    def _load_user_cache(self) -> Dict:
        """
        加载用户缓存

        Returns:
            Dict: 用户缓存数据
        """
        try:
            if os.path.exists(self.user_cache_file):
                with open(self.user_cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cutoff = time.time() - 604800  # 7天
                return {
                    k: v for k, v in data.items()
                    if v.get("timestamp", 0) > cutoff
                }
        except Exception as e:
            print(f"[Cache] 加载用户缓存失败: {e}")
        return {}

    def _load_event_cache(self) -> Dict:
        """
        加载事件缓存，兼容旧格式

        Returns:
            Dict: 事件缓存数据
        """
        try:
            if os.path.exists(self.event_cache_file):
                with open(self.event_cache_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # 兼容旧版事件缓存格式（列表转字典）
                if isinstance(raw_data, list):
                    return {k: time.time() for k in raw_data}

                cutoff = time.time() - 32 * 3600
                return {k: float(v) for k, v in raw_data.items() if float(v) > cutoff}

        except Exception as e:
            print(f"[Cache] 加载事件缓存失败: {e}")
        return {}

    def save_all(self):
        """保存所有缓存"""
        self.save_user_cache()
        self.save_event_cache()

    def save_user_cache(self):
        """保存用户缓存"""
        self._atomic_save(self.user_cache_file, self.user_cache)

    def save_event_cache(self):
        """保存事件缓存，保持与旧格式兼容"""
        processed_events = {k: str(v) for k, v in self.event_cache.items()}
        self._atomic_save(self.event_cache_file, processed_events)

    def _atomic_save(self, filename: str, data: Dict):
        """
        原子化保存

        Args:
            filename: 文件路径
            data: 要保存的数据
        """
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            temp_file = filename + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, filename)
        except Exception as e:
            print(f"[Cache] 保存失败 {filename}: {e}")

    # 用户缓存方法
    def get_user_name(self, user_id: str) -> Optional[str]:
        """
        获取缓存的用户名

        Args:
            user_id: 用户ID

        Returns:
            Optional[str]: 用户名，若不存在则返回None
        """
        entry = self.user_cache.get(user_id, {})
        if entry:
            return entry["name"]
        return None

    def update_user(self, user_id: str, name: str):
        """
        更新用户缓存

        Args:
            user_id: 用户ID
            name: 用户名
        """
        self.user_cache[user_id] = {
            "name": name,
            "timestamp": time.time()
        }

    # 事件缓存方法
    def check_event(self, event_id: str) -> bool:
        """
        检查事件是否已处理

        Args:
            event_id: 事件ID

        Returns:
            bool: 是否已处理
        """
        return event_id in self.event_cache

    def add_event(self, event_id: str):
        """
        记录已处理事件

        Args:
            event_id: 事件ID
        """
        self.event_cache[event_id] = time.time()