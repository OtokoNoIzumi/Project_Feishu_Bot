"""
飞书机器人服务主入口（解耦版）

该模块提供了一个解耦后的飞书机器人服务入口，将业务逻辑与平台实现分离
"""

import os
import sys
import json
import time
import asyncio
import threading
from pathlib import Path
from dotenv import load_dotenv
from gradio_client import Client
import datetime
# 添加当前目录到系统路径
is_not_jupyter = "__file__" in globals()
if is_not_jupyter:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.normpath(os.path.join(current_dir, ".."))
else:
    current_dir = os.getcwd()
    current_dir = os.path.join(current_dir, "..")
    root_dir = os.path.normpath(os.path.join(current_dir))

current_dir = os.path.normpath(current_dir)
sys.path.append(current_dir)

# 导入核心模块
from Module.Core.cache_service import CacheService
from Module.Core.config_service import ConfigService
from Module.Core.media_service import MediaService
from Module.Core.bot_service import BotService
from Module.Core.scheduler import SchedulerService
from Module.Platforms.feishu import FeishuPlatform
from Module.Common.scripts.common import debug_utils


def setup_services():
    """设置所有服务组件"""
    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    # 创建配置服务
    config_service = ConfigService(os.getenv("AUTH_CONFIG_FILE_PATH", ""))

    # config_service = ConfigService(os.path.join(current_dir, "config.json"))

    # 创建缓存服务
    cache_dir = os.path.join(current_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_service = CacheService(cache_dir)

    # 创建Gradio客户端
    gradio_url = f"https://{os.getenv('SERVER_ID', '')}"
    gradio_client = Client(gradio_url)

    # 创建Coze API设置
    coze_api_settings = {
        "api_base": config_service.get("coze_bot_url", "https://api.coze.cn/v1/workflow/run"),
        "workflow_id": config_service.get("bot_id", ""),
        "access_token": os.getenv("COZE_API_KEY", ""),
        "voice_id": config_service.get("voice_id", "peach")
    }

    # 创建媒体服务
    media_service = MediaService(
        ffmpeg_path=os.getenv("FFMPEG_PATH", ""),
        gradio_client=gradio_client,
        coze_api_settings=coze_api_settings
    )

    # 创建机器人服务
    bot_service = BotService(
        cache_service=cache_service,
        config_service=config_service,
        media_service=media_service,
        admin_id=os.getenv("ADMIN_ID", "")
    )

    # 创建调度器服务
    scheduler_service = SchedulerService()

    # 配置定时任务
    # 示例：每天10:30发送日程 (你可以保留或按需修改/删除)
    scheduler_service.add_daily_task(
        task_name="daily_schedule_main", # 给一个唯一的任务名
        time_str="07:30",
        # time_str="13:54",
        task_func=bot_service.send_daily_schedule
    )

    # 任务1: 每天下午15:30，不指定source (send_bilibili_updates将不传sources参数)
    scheduler_service.add_daily_task(
        task_name="bili_updates_afternoon",
        time_str="15:30",
        task_func=bot_service.send_bilibili_updates
    )

    # 任务2: 每天的23:55，source包括favorites和dynamic
    scheduler_service.add_daily_task(
        task_name="bili_updates_night",
        time_str="23:55",
        task_func=bot_service.send_bilibili_updates,
        sources=["favorites", "dynamic"]  # 作为关键字参数传递
    )

    # 创建平台实现
    platform = FeishuPlatform()
    platform.initialize({
        "app_id": os.getenv("FEISHU_APP_MESSAGE_ID", ""),
        "app_secret": os.getenv("FEISHU_APP_MESSAGE_SECRET", ""),
        "log_level": config_service.get("log_level", "DEBUG")
    })

    # 注册机器人服务
    platform.register_bot_service(bot_service)

    return platform, scheduler_service


def main():
    """程序入口函数"""
    platform, scheduler_service = setup_services()

    # 启动平台服务（在后台线程中）
    debug_utils.log_and_print("准备启动飞书机器人服务...", log_level="INFO")
    platform_thread = threading.Thread(target=platform.start, daemon=True)
    platform_thread.start()
    debug_utils.log_and_print("飞书机器人服务已在后台线程启动。", log_level="INFO")

    # 主循环，运行调度器
    debug_utils.log_and_print("启动调度器主循环...", log_level="INFO")
    try:
        while True:
            scheduler_service.run_pending()
            time.sleep(1) # 降低CPU占用，可以根据调度任务的精度调整
    except KeyboardInterrupt:
        debug_utils.log_and_print("程序被用户中断", log_level="INFO")
    finally:
        debug_utils.log_and_print("正在停止飞书机器人服务...", log_level="INFO")
        platform.stop() # 尝试停止平台服务
        # platform_thread.join() # 等待平台线程结束（可选，如果stop是阻塞的或者你想确保它完全关闭）
        debug_utils.log_and_print("飞书机器人服务已停止。", log_level="INFO")


async def main_jupyter():
    """Jupyter环境下的入口函数"""
    platform, scheduler_service = setup_services()

    # 启动平台服务
    debug_utils.log_and_print("启动飞书机器人服务...", log_level="INFO")
    await platform.start_async()  # 异步方式启动平台

    # 异步主循环
    try:
        while True:
            scheduler_service.run_pending()
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        debug_utils.log_and_print("程序被用户中断", log_level="INFO")
    finally:
        await platform.stop_async()
        debug_utils.log_and_print("飞书机器人服务已停止", log_level="INFO")


if __name__ == "__main__":
    if is_not_jupyter:
        main()
    else:
        print("Jupyter环境")
        # await main_jupyter()  # 导出时要注释掉
