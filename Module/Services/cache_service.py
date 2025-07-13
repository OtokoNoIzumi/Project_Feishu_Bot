"""
缓存服务

提供缓存管理功能，包括用户信息缓存和事件缓存
原位置：Module/Core/cache_service.py
"""

import os
import json
import time
import datetime
from typing import Dict, Any, Optional
from collections import OrderedDict

from .service_decorators import service_operation_safe, file_processing_safe, cache_operation_safe


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
        self.message_id_card_id_mapping_file = os.path.join(cache_dir, "message_id_card_id_mapping.json")

        # 用户缓存结构：{open_id: {"name": str, "timestamp": float}}
        self.user_cache: Dict[str, Dict] = self._load_user_cache()

        # 事件缓存结构：{event_id: timestamp}
        self.event_cache: Dict[str, float] = self._load_event_cache()

        # message_id和card_id的映射
        self.message_id_card_id_mapping: OrderedDict[str, Dict[str, Any]] = self._load_message_id_card_id_mapping()

        self.clear_expired()

    # ===============缓存加载=================
    @cache_operation_safe("用户缓存加载失败", return_value={})
    def _load_user_cache(self) -> Dict:
        """
        加载用户缓存

        Returns:
            Dict: 用户缓存数据
        """
        if os.path.exists(self.user_cache_file):
            with open(self.user_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cutoff = time.time() - 604800  # 7天
            return {
                k: v for k, v in data.items()
                if v.get("timestamp", 0) > cutoff
            }
        return {}

    @cache_operation_safe("事件缓存加载失败", return_value={})
    def _load_event_cache(self) -> Dict:
        """
        加载事件缓存，兼容旧格式

        Returns:
            Dict: 事件缓存数据
        """
        if os.path.exists(self.event_cache_file):
            with open(self.event_cache_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            cutoff = time.time() - 32 * 3600
            return {k: float(v) for k, v in raw_data.items() if float(v) > cutoff}

        return {}

    @cache_operation_safe("message_id和card_id的映射加载失败", return_value=OrderedDict())
    def _load_message_id_card_id_mapping(self) -> OrderedDict[str, Dict[str, Any]]:
        """加载message_id和card_id的映射，按创建时间倒序排列"""
        if os.path.exists(self.message_id_card_id_mapping_file):
            with open(self.message_id_card_id_mapping_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 按create_date倒序排序，最新的在前面
            sorted_items = sorted(
                data.items(),
                key=lambda x: x[1].get("create_date", "1970-01-01 00:00:00"),
                reverse=True
            )

            return OrderedDict(sorted_items)
        return OrderedDict()

    def save_all(self):
        """保存所有缓存"""
        self.save_user_cache()
        self.save_event_cache()
        self.save_message_id_card_id_mapping()

    def save_user_cache(self):
        """保存用户缓存"""
        self._atomic_save(self.user_cache_file, self.user_cache)

    def save_event_cache(self):
        """保存事件缓存，保持与旧格式兼容"""
        processed_events = {k: str(v) for k, v in self.event_cache.items()}
        self._atomic_save(self.event_cache_file, processed_events)

    def save_message_id_card_id_mapping(self):
        """保存message_id和card_id的映射，按创建时间倒序保存"""
        # 确保保存时按create_date倒序排列
        sorted_items = sorted(
            self.message_id_card_id_mapping.items(),
            key=lambda x: x[1].get("create_date", "1970-01-01 00:00:00"),
            reverse=True
        )
        ordered_data = OrderedDict(sorted_items)
        self._atomic_save(self.message_id_card_id_mapping_file, ordered_data)

    @file_processing_safe("缓存文件保存失败")
    def _atomic_save(self, filename: str, data: Dict):
        """
        原子化保存

        Args:
            filename: 文件路径
            data: 要保存的数据
        """
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        temp_file = filename + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, filename)

    # ===============用户相关=================
    # 原有接口保持不变
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

    # ===============事件id相关=================
    def check_event(self, event_id: str) -> bool:
        """
        检查事件是否已处理

        Args:
            event_id: 事件ID

        Returns:
            bool: 是否已处理
        """
        return event_id in self.event_cache

    def get_event_timestamp(self, event_id: str):
        """
        记录已处理事件

        Args:
            event_id: 事件ID
        """
        return self.event_cache.get(event_id, None)

    def add_event(self, event_id: str):
        """
        记录已处理事件

        Args:
            event_id: 事件ID
        """
        self.event_cache[event_id] = time.time()

    # ===============卡片相关=================
    # 新增：message_id和card_id的映射
    def update_message_id_card_id_mapping(self, message_id: str, card_id: str, card_name: str = ""):
        info = self.get_card_info(message_id)
        sequence = info.get("sequence", 0) + 1
        create_date = info.get("create_date") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_card_name = card_name or info.get("card_name", "")

        self.message_id_card_id_mapping[message_id] = {
            "card_id": card_id,
            "card_name": new_card_name,
            "sequence": sequence,
            "create_date": create_date,
        }

    def get_card_info(self, message_id: str) -> Optional[Dict[str, Any]]:
        """获取card_id"""
        return self.message_id_card_id_mapping.get(message_id, {})

    # ===============管理缓存=================
    # 新增：简单的状态查询方法（为后续API做准备）
    def get_status(self) -> Dict[str, Any]:
        """获取缓存状态信息"""
        return {
            "user_cache_size": len(self.user_cache),
            "event_cache_size": len(self.event_cache),
            "message_id_card_id_mapping_size": len(self.message_id_card_id_mapping),
            "cache_dir": self.cache_dir,
            "files": {
                "user_cache_exists": os.path.exists(self.user_cache_file),
                "event_cache_exists": os.path.exists(self.event_cache_file),
                "message_id_card_id_mapping_exists": os.path.exists(self.message_id_card_id_mapping_file)
            }
        }

    def clear_expired(self) -> Dict[str, int]:
        """清理过期缓存，返回清理数量"""
        # 清理过期用户缓存（7天）
        cutoff_user = time.time() - 604800
        before_user = len(self.user_cache)
        self.user_cache = {
            k: v for k, v in self.user_cache.items()
            if v.get("timestamp", 0) > cutoff_user
        }
        if before_user != len(self.user_cache):
            self.save_user_cache()

        # 清理过期事件缓存（32小时）
        cutoff_event = time.time() - 32 * 3600
        before_event = len(self.event_cache)
        self.event_cache = {
            k: v for k, v in self.event_cache.items()
            if v > cutoff_event
        }
        if before_event != len(self.event_cache):
            self.save_event_cache()

        # 清理过期message_id和card_id的映射（1天）
        cutoff_message_id_card_id_mapping = datetime.datetime.now() - datetime.timedelta(days=1)
        before_message_id_card_id_mapping = len(self.message_id_card_id_mapping)
        filtered_items = {
            k: v for k, v in self.message_id_card_id_mapping.items()
            if datetime.datetime.strptime(v.get("create_date", "1970-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S") >= cutoff_message_id_card_id_mapping
        }
        self.message_id_card_id_mapping = OrderedDict(filtered_items)
        if before_message_id_card_id_mapping != len(self.message_id_card_id_mapping):
            self.save_message_id_card_id_mapping()

        return {
            "user_cache_cleared": before_user - len(self.user_cache),
            "event_cache_cleared": before_event - len(self.event_cache),
            "message_id_card_id_mapping_cleared": before_message_id_card_id_mapping - len(self.message_id_card_id_mapping)
        }
