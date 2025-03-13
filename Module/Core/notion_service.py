"""
Notion服务模块

该模块提供与Notion数据库的交互功能，特别用于获取和管理B站视频数据
"""

import os
import time
import json
import random
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
from Module.Common.scripts import DataSource_Notion as dsn
from Module.Core.cache_service import CacheService


class NotionService:
    """Notion服务，提供与Notion数据库的交互功能"""

    def __init__(self, cache_service: CacheService):
        """
        初始化Notion服务

        Args:
            cache_service: 缓存服务
        """
        self.cache_service = cache_service
        self.token = os.environ.get("NOTION_TOKEN")
        self.database_path = os.environ.get("DATABASE_PATH")

        if not self.token:
            raise ValueError("未提供Notion API令牌，请设置NOTION_TOKEN环境变量")
        if not self.database_path:
            raise ValueError("未提供Notion数据库路径，请设置DATABASE_PATH环境变量")

        # Notion客户端
        self.notion_manager = dsn.NotionDatabaseManager(token=self.token)

        # 缓存键名
        self.bili_cache_key = "bili_videos_cache"
        self.bili_cache_time_key = "bili_videos_cache_time"

        # 缓存有效期（秒）
        self.cache_expiry = 7200  # 2小时

        # 初始化数据
        self.cache_file = os.path.join(self.cache_service.cache_dir, "notion_bili_cache.json")
        self._load_cache()

    def _load_cache(self) -> None:
        """加载本地缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache_data = json.load(f)
            else:
                self.cache_data = {
                    self.bili_cache_key: [],
                    self.bili_cache_time_key: 0
                }
        except Exception as e:
            print(f"[NotionService] 加载缓存失败: {e}")
            self.cache_data = {
                self.bili_cache_key: [],
                self.bili_cache_time_key: 0
            }

    def _save_cache(self) -> None:
        """保存缓存到本地"""
        try:
            os.makedirs(self.cache_service.cache_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[NotionService] 保存缓存失败: {e}")

    async def _fetch_bili_videos_from_notion(self) -> List[Dict]:
        """
        从Notion获取B站视频数据

        Returns:
            List[Dict]: B站视频数据列表
        """
        # 过滤条件：未读的视频
        filter_dict = {
            "and": [
                {
                    "property": "时间提醒",
                    "rich_text": {"does_not_contain": "已"}
                },
                {
                    "property": "优先级",
                    "select": {"is_not_empty": True}
                },
                {
                    "property": "URL",
                    "url": {"is_not_empty": True}
                }
            ]
        }

        # 获取数据
        df = await self.notion_manager.get_dataframe_from_database(
            database_id=self.database_path,
            filter_dict=filter_dict,
            sort_columns="优先级",
            max_item_count=100
        )

        # 过滤掉"场合"为"避免手机"的视频
        if "场合" in df.columns:
            df = df[~df["场合"].str.contains("避免手机", na=False)]

        # 定义内容来源的映射
        source_mapping = {
            "homepage": "主页推送",
            "dynamic": "关注动态",
            "favorites": "收藏夹"
        }

        # 优先级映射
        priority_mapping = {
            "High": "高",
            "Medium": "中",
            "Low": "低"
        }

        # 转换为字典列表
        videos = []
        for _, row in df.iterrows():
            # 将内容来源转换为中文
            source = row.get("内容来源", "")
            chinese_source = source_mapping.get(source, source)

            # 优先级转换为中文
            priority = row.get("优先级", "Low")
            chinese_priority = priority_mapping.get(priority, "低")

            # 将时间汇总转换为分钟:秒格式
            duration_minutes = row.get("时间汇总", 0)*60
            minutes = int(duration_minutes)
            seconds = int((duration_minutes - minutes) * 60)
            duration_str = f"{minutes}分{seconds}秒" if seconds else f"{minutes}分钟"

            video = {
                "pageid": row.get("pageid", ""),
                "title": row.get("待办事项", "无标题视频"),
                "url": row.get("URL", ""),
                "author": row.get("作者", ""),
                "priority": priority,
                "chinese_priority": chinese_priority,
                "duration": duration_minutes,  # 转换为秒
                "duration_str": duration_str,
                "summary": row.get("推荐概要", ""),
                "upload_date": row.get("投稿日期", "").split(" ")[0],
                "source": source,
                "chinese_source": chinese_source
            }
            videos.append(video)

        return videos

    def _is_cache_valid(self) -> bool:
        """
        检查缓存是否有效

        Returns:
            bool: 缓存是否有效
        """
        cache_time = self.cache_data.get(self.bili_cache_time_key, 0)
        return (time.time() - cache_time) < self.cache_expiry

    async def get_bili_video(self) -> Dict:
        """
        获取一个B站视频推荐

        Returns:
            Dict: B站视频信息
        """
        # 检查缓存是否有效
        if not self._is_cache_valid() or not self.cache_data.get(self.bili_cache_key):
            # 更新缓存
            videos = await self._fetch_bili_videos_from_notion()
            self.cache_data[self.bili_cache_key] = videos
            self.cache_data[self.bili_cache_time_key] = time.time()
            self._save_cache()

        videos = self.cache_data.get(self.bili_cache_key, [])
        if not videos:
            return {
                "title": "暂无推荐视频",
                "url": "",
                "pageid": "",
                "success": False
            }

        # 按优先级和时长分组选择视频
        video = self._select_video_by_priority(videos)
        return {
            "title": video.get("title", "无标题视频"),
            "url": video.get("url", ""),
            "pageid": video.get("pageid", ""),
            "success": True,
            "author": video.get("author", ""),
            "duration_str": video.get("duration_str", ""),
            "chinese_priority": video.get("chinese_priority", ""),
            "chinese_source": video.get("chinese_source", ""),
            "summary": video.get("summary", ""),
            "upload_date": video.get("upload_date", ""),
        }

    def _select_video_by_priority(self, videos: List[Dict]) -> Dict:
        """
        根据优先级和时长选择视频

        Args:
            videos: 视频列表

        Returns:
            Dict: 选中的视频
        """
        # 创建分组
        # 1. 10分钟内、优先级High
        # 2. 10分钟内、优先级Medium
        # 3. 10分钟外、优先级High
        # 4. 10分钟内、优先级Low
        # 5. 10分钟外、优先级Medium
        # 6. 10分钟外、优先级Low

        groups = [
            [v for v in videos if v.get("duration", 0) <= 10 and v.get("priority") == "High"],
            [v for v in videos if v.get("duration", 0) <= 10 and v.get("priority") == "Medium"],
            [v for v in videos if v.get("duration", 0) > 10 and v.get("priority") == "High"],
            [v for v in videos if v.get("duration", 0) <= 10 and v.get("priority") == "Low"],
            [v for v in videos if v.get("duration", 0) > 10 and v.get("priority") == "Medium"],
            [v for v in videos if v.get("duration", 0) > 10 and v.get("priority") == "Low"],
        ]

        # 从非空分组中选择
        for group in groups:
            if group:
                return random.choice(group)

        # 如果所有分组都为空，则从所有视频中随机选择
        return random.choice(videos)

    async def mark_video_as_read(self, pageid: str) -> bool:
        """
        将视频标记为已读

        Args:
            pageid: Notion页面ID

        Returns:
            bool: 是否成功
        """
        if not pageid:
            return False

        try:
            # 更新Notion页面属性
            today_date = datetime.now().strftime("%Y-%m-%d")
            page_properties = {
                "完成日期": {"date": {"start": today_date, "end": None}}
            }

            await self.notion_manager.update_page_properties(pageid, page_properties)

            # 更新缓存
            if self.bili_cache_key in self.cache_data:
                self.cache_data[self.bili_cache_key] = [
                    v for v in self.cache_data[self.bili_cache_key]
                    if v.get("pageid") != pageid
                ]
                self._save_cache()

            return True
        except Exception as e:
            print(f"[NotionService] 标记视频已读失败: {e}")
            return False