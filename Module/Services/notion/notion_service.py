"""
Notion服务模块

该模块提供与Notion数据库的交互功能，特别用于获取和管理B站视频数据
"""

import os
import time
import json
import random
from typing import Dict, List, Any, Optional
from datetime import datetime

import pandas as pd
from Module.Common.scripts import DataSource_Notion as dsn
from Module.Services.cache_service import CacheService
from Module.Common.scripts.common import debug_utils


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

        # 本地已读状态跟踪（用于卡片显示）
        self._local_read_status = set()  # 存储已读的pageid
        self._read_status_cache_key = "local_read_status"

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
                    self.bili_cache_time_key: 0,
                    self._read_status_cache_key: []
                }

            # 加载本地已读状态
            read_status_list = self.cache_data.get(self._read_status_cache_key, [])
            self._local_read_status = set(read_status_list)

        except Exception as e:
            debug_utils.log_and_print(f"[NotionService] 加载缓存失败: {e}", log_level="ERROR")
            self.cache_data = {
                self.bili_cache_key: [],
                self.bili_cache_time_key: 0,
                self._read_status_cache_key: []
            }
            self._local_read_status = set()

    def _save_cache(self) -> None:
        """保存缓存到本地"""
        try:
            # 更新已读状态到缓存数据
            self.cache_data[self._read_status_cache_key] = list(self._local_read_status)

            os.makedirs(self.cache_service.cache_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            debug_utils.log_and_print(f"[NotionService] 保存缓存失败: {e}", log_level="ERROR")

    def _is_cache_valid(self) -> bool:
        """
        检查缓存是否有效

        Returns:
            bool: 缓存是否有效
        """
        cache_time = self.cache_data.get(self.bili_cache_time_key, 0)
        return (time.time() - cache_time) < self.cache_expiry

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
        videos = [v for v in videos if v.get("unread", True)]
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
        return random.choice(videos) if videos else {}

    def get_bili_video(self) -> Dict:
        """
        获取一个B站视频推荐

        Returns:
            Dict: B站视频信息
        """
        # 检查缓存是否有效
        if not self._is_cache_valid() or not self.cache_data.get(self.bili_cache_key):
            # 更新缓存是异步的，这里同步执行一次
            self._update_bili_cache_sync()

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

    def _update_bili_cache_sync(self) -> None:
        """
        同步更新B站视频缓存

        通过异步转同步的方式获取Notion数据
        """
        try:
            # 使用更可靠的同步执行异步代码的方式
            videos = self._sync_run_coroutine(self._fetch_bili_videos_from_notion())

            # 更新缓存
            self.cache_data[self.bili_cache_key] = videos
            self.cache_data[self.bili_cache_time_key] = time.time()
            self._save_cache()

            debug_utils.log_and_print(f"[NotionService] 成功更新B站视频缓存，获取到 {len(videos)} 条记录", log_level="INFO")
        except Exception as e:
            debug_utils.log_and_print(f"[NotionService] 更新B站视频缓存失败: {e}", log_level="ERROR")
            import traceback
            traceback.print_exc()

    def _sync_run_coroutine(self, coroutine):
        """
        安全地同步执行异步协程

        Args:
            coroutine: 要执行的异步协程

        Returns:
            协程的执行结果
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        try:
            # 尝试获取当前运行的事件循环
            asyncio.get_running_loop()
            # 如果没有抛出异常，说明当前已有事件循环在运行
            # 使用线程池在新线程中运行事件循环
            with ThreadPoolExecutor() as pool:
                # 在线程池中创建新的事件循环并运行协程
                return pool.submit(lambda: self._run_in_new_loop(coroutine)).result()
        except RuntimeError:
            # 如果获取不到事件循环，说明不在事件循环中
            # 直接创建新的事件循环运行
            return self._run_in_new_loop(coroutine)

    def _run_in_new_loop(self, coroutine):
        """
        在新的事件循环中运行协程

        Args:
            coroutine: 要执行的异步协程

        Returns:
            协程的执行结果
        """
        import asyncio

        # 确保有一个事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 运行协程并获取结果
        try:
            return loop.run_until_complete(coroutine)
        finally:
            # 不关闭事件循环，避免影响其他可能的异步操作
            pass

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
            "High": "💖高",
            "Medium": "😜中",
            "Low": "👾低"
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
            duration_minutes = row.get("预估量", 0)
            hour_switch = row.get("预估单位", "分钟")
            if hour_switch == "小时":
                duration_minutes = duration_minutes * 60
            # 如果是小数，转为分钟:秒格式
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
                "duration": duration_minutes,  # 时长（分钟）
                "duration_str": duration_str,
                "summary": row.get("推荐概要", ""),
                "upload_date": str(row.get("投稿日期", "")).split(" ")[0],
                "source": source,
                "chinese_source": chinese_source,
                "unread": True
            }
            videos.append(video)

        return videos

    def mark_video_as_read(self, pageid: str) -> bool:
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
            # 更新Notion页面属性 (同步方式)
            today_date = datetime.now().strftime("%Y-%m-%d")
            page_properties = {
                "完成日期": {"date": {"start": today_date, "end": None}}
            }

            # 启动一个异步任务更新Notion，但不等待完成
            self._update_notion_property_async(pageid, page_properties)

            # 更新本地缓存 (这部分是同步的)
            if self.bili_cache_key in self.cache_data:
                for v in self.cache_data[self.bili_cache_key]:
                    if v.get("pageid") == pageid:
                        v["unread"] = False

            # 添加到本地已读状态跟踪
            self._local_read_status.add(pageid)
            self._save_cache()

            return True
        except Exception as e:
            debug_utils.log_and_print(f"[NotionService] 标记视频已读失败: {e}", log_level="ERROR")
            return False

    def is_video_read(self, pageid: str) -> bool:
        """
        检查视频是否已读

        Args:
            pageid: Notion页面ID

        Returns:
            bool: 是否已读
        """
        return pageid in self._local_read_status

    def get_video_by_id(self, pageid: str) -> Dict:
        """
        根据页面ID获取视频信息

        Args:
            pageid: Notion页面ID

        Returns:
            Dict: 视频信息
        """
        if not pageid:
            return None

        try:
            # 获取页面信息
            page_info = self.cache_data.get(self.bili_cache_key, [])
            # 查找匹配的视频信息
            matching_videos = [v for v in page_info if v.get("pageid") == pageid]
            if not matching_videos:
                return None
            page_info = matching_videos[0]
            if not page_info:
                return None
            # 构建视频信息
            video = {
                "pageid": pageid,
                "title": page_info.get("title", "无标题视频"),
                "url": page_info.get("url", ""),
                "author": page_info.get("author", ""),
                "priority": page_info.get("priority", ""),
                "chinese_priority": page_info.get("chinese_priority", ""),
                "duration": page_info.get("duration", 0),
                "duration_str": page_info.get("duration_str", ""),
                "summary": page_info.get("summary", ""),
                "upload_date": page_info.get("upload_date", ""),
                "source": page_info.get("source", ""),
                "chinese_source": page_info.get("chinese_source", ""),
                "success": True
            }

            return video
        except Exception as e:
            debug_utils.log_and_print(f"[NotionService] 获取视频信息失败: {e}", log_level="ERROR")
            return None

    def _update_notion_property_async(self, page_id: str, page_properties: Dict) -> None:
        """
        异步更新Notion页面属性 (在后台线程中执行)

        Args:
            page_id: Notion页面ID
            page_properties: 要更新的属性
        """
        import threading

        # 创建后台任务函数
        def run_async_update():
            try:
                # 使用安全的同步执行方式
                self._sync_run_coroutine(self._update_page_properties_async(page_id, page_properties))
                debug_utils.log_and_print(f"[NotionService] 成功更新页面属性: {page_id}", log_level="INFO")
            except Exception as e:
                debug_utils.log_and_print(f"[NotionService] 更新页面属性失败: {e}", log_level="ERROR")
                import traceback
                traceback.print_exc()

        # 启动一个新线程执行异步操作
        thread = threading.Thread(target=run_async_update)
        thread.daemon = True  # 设为守护线程，避免阻塞主程序退出
        thread.start()
        # 不等待线程完成，继续执行主线程

    async def _update_page_properties_async(self, page_id: str, page_properties: Dict) -> None:
        """
        更新Notion页面属性的异步实现

        Args:
            page_id: Notion页面ID
            page_properties: 要更新的属性
        """
        await self.notion_manager.update_page_properties(page_id, page_properties)

    def get_bili_videos_multiple(self) -> Dict:
        """
        获取多个B站视频推荐（1个主推荐 + 最多3个额外推荐）

        Returns:
            Dict: 包含主视频和额外视频列表的结果
        """
        # 检查缓存是否有效
        if not self._is_cache_valid() or not self.cache_data.get(self.bili_cache_key):
            # 更新缓存是异步的，这里同步执行一次
            self._update_bili_cache_sync()

        videos = self.cache_data.get(self.bili_cache_key, [])
        if not videos:
            return {
                "main_video": {
                    "title": "暂无推荐视频",
                    "url": "",
                    "pageid": "",
                    "success": False
                },
                "additional_videos": [],
                "success": False
            }

        # 按优先级和时长分组选择主视频
        main_video = self._select_video_by_priority(videos)

        # 获取额外的3个不同视频（排除主视频）
        additional_videos = []
        remaining_videos = [v for v in videos if v.get("pageid") != main_video.get("pageid") and v.get("unread", True)]

        # 从剩余视频中选择最多3个，优先选择不同优先级和来源的视频
        if remaining_videos:
            # 按优先级和来源分组，确保多样性
            priority_groups = {
                "High": [v for v in remaining_videos if v.get("priority") == "High"],
                "Medium": [v for v in remaining_videos if v.get("priority") == "Medium"],
                "Low": [v for v in remaining_videos if v.get("priority") == "Low"]
            }

            # 从每个优先级组中选择1个，最多3个
            for priority in ["High", "Medium", "Low"]:
                if len(additional_videos) >= 3:
                    break
                group = priority_groups.get(priority, [])
                if group:
                    selected = random.choice(group)
                    additional_videos.append(selected)
                    # 从其他组中移除这个视频，避免重复
                    for p in priority_groups:
                        priority_groups[p] = [v for v in priority_groups[p] if v.get("pageid") != selected.get("pageid")]

        # 格式化主视频
        main_video_formatted = {
            "title": main_video.get("title", "无标题视频"),
            "url": main_video.get("url", ""),
            "pageid": main_video.get("pageid", ""),
            "success": True,
            "author": main_video.get("author", ""),
            "duration_str": main_video.get("duration_str", ""),
            "chinese_priority": main_video.get("chinese_priority", ""),
            "chinese_source": main_video.get("chinese_source", ""),
            "summary": main_video.get("summary", ""),
            "upload_date": main_video.get("upload_date", ""),
        }

        # 格式化额外视频（简化信息）
        additional_videos_formatted = []
        for video in additional_videos:
            additional_videos_formatted.append({
                "title": video.get("title", "无标题视频"),
                "url": video.get("url", ""),
                "pageid": video.get("pageid", ""),
                "duration_str": video.get("duration_str", ""),
                "author": video.get("author", ""),
                "chinese_priority": video.get("chinese_priority", ""),
                "chinese_source": video.get("chinese_source", "")
            })

        return {
            "main_video": main_video_formatted,
            "additional_videos": additional_videos_formatted,
            "success": True
        }

    def get_bili_videos_statistics(self) -> Dict:
        """
        获取B站视频统计信息（用于7:30定时任务）

        Returns:
            Dict: 统计信息（字段内容全部为中文）
        """
        # 检查缓存是否有效
        if not self._is_cache_valid() or not self.cache_data.get(self.bili_cache_key):
            # 更新缓存是异步的，这里同步执行一次
            self._update_bili_cache_sync()

        videos = self.cache_data.get(self.bili_cache_key, [])
        unread_videos = [v for v in videos if v.get("unread", True)]

        if not unread_videos:
            return {
                "total_count": 0,
                "priority_stats": {},
                "duration_stats": {},
                "source_stats": {},
                "top_recommendations": [],
                "success": False
            }

        # 统计各维度数据
        priority_stats = {}
        # 用中文key替换
        duration_stats = {"短视频": 0, "中视频": 0, "长视频": 0}  # ≤10分钟, 10-30分钟, >30分钟
        source_stats = {}

        # # 优先级中文映射
        # priority_map = {
        #     "High": "💖高",
        #     "Medium": "😜中",
        #     "Low": "👾低",
        #     "Unknown": "未知优先级"
        # }

        for video in unread_videos:
            # 优先级统计
            priority = video.get("chinese_priority", "Unknown")
            # priority = priority_map.get(priority_en, priority_en)
            if priority not in priority_stats:
                priority_stats[priority] = {"数量": 0, "总时长分钟": 0}

            priority_stats[priority]["数量"] += 1

            # 获取时长（分钟） - duration字段已经是数字类型
            duration_minutes = video.get("duration", 0)
            try:
                total_minutes = float(duration_minutes) if duration_minutes else 0
                priority_stats[priority]["总时长分钟"] += int(total_minutes)
            except (ValueError, TypeError):
                # 如果转换失败，跳过时长计算
                total_minutes = 0

            # 时长统计
            if total_minutes <= 10:
                duration_stats["短视频"] += 1
            elif total_minutes <= 30:
                duration_stats["中视频"] += 1
            else:
                duration_stats["长视频"] += 1

            # 来源统计
            source = video.get("chinese_source", "未知来源")
            source_stats[source] = source_stats.get(source, 0) + 1

        # 获取前3个推荐视频（按优先级排序：高>中>低）
        top_recommendations = []

        # 按优先级分组
        high_priority = [v for v in unread_videos if v.get("chinese_priority") == "💖高"]
        medium_priority = [v for v in unread_videos if v.get("chinese_priority") == "😜中"]
        low_priority = [v for v in unread_videos if v.get("chinese_priority") == "👾低"]

        # 按优先级依次选择，每个优先级内随机选择
        selected_videos = []
        for priority_group in [high_priority, medium_priority, low_priority]:
            if len(selected_videos) >= 3:
                break

            # 从当前优先级组中随机选择，直到达到3个或该组用完
            available = [v for v in priority_group if v not in selected_videos]
            while available and len(selected_videos) < 3:
                selected = random.choice(available)
                selected_videos.append(selected)
                available.remove(selected)

        # 格式化推荐视频（字段内容中文）
        for video in selected_videos:
            top_recommendations.append({
                "标题": video.get("title", "无标题视频"),
                "链接": video.get("url", ""),
                "页面ID": video.get("pageid", ""),
                "时长": video.get("duration_str", ""),
                "优先级": video.get("chinese_priority", ""),
                "来源": video.get("chinese_source", "")
            })

        return {
            "总未读数": len([v for v in videos if v.get("unread", True)]),
            "优先级统计": priority_stats,
            "时长分布": duration_stats,
            "来源统计": source_stats,
            "今日精选推荐": top_recommendations,
            "success": True
        }