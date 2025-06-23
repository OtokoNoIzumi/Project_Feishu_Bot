"""
飞书机器人 - 生产版本

功能特性：
- 基础交互：文本对话、菜单点击、卡片交互
- 音频处理：TTS语音合成、格式转换
- 图像处理：AI图像生成、图像风格转换
- B站推荐：智能推荐、已读管理、数据统计
- 定时任务：事件驱动架构、静默模式
- HTTP API：RESTful接口、安全鉴权
- 四层架构：完整实现和统一服务管理
"""

import os
import sys
import asyncio
import threading
import time
from pathlib import Path
import argparse
from dotenv import load_dotenv
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from Module.Application.app_controller import AppController
from Module.Business.message_processor import MessageProcessor
from Module.Adapters import FeishuAdapter
from Module.Services.constants import ServiceNames, SchedulerConstKeys
from Module.Common.scripts.common import debug_utils
from Module.Services.service_decorators import require_service


def setup_application():
    """设置应用组件"""
    load_dotenv(os.path.join(current_dir, ".env"))

    print("🚀 飞书机器人启动中...")

    # 创建应用控制器
    app_controller = AppController(project_root_path=str(current_dir))

    # 注册服务
    registration_results = app_controller.auto_register_services()
    success_count = sum(1 for success in registration_results.values() if success)
    total_count = len(registration_results)

    if success_count == total_count:
        print(f"✅ 服务注册完成 ({success_count}/{total_count})")
    else:
        print(f"⚠️ 服务注册部分成功 ({success_count}/{total_count})")
        failed_services = [name for name, success in registration_results.items() if not success]
        debug_utils.log_and_print(f"❌ 失败的服务: {failed_services}", log_level="WARNING")

    # 创建核心组件
    message_processor = MessageProcessor(app_controller=app_controller)
    feishu_adapter = FeishuAdapter(
        message_processor=message_processor,
        app_controller=app_controller
    )

    # 建立定时任务事件监听
    scheduler_service = app_controller.get_service(ServiceNames.SCHEDULER)
    if scheduler_service:
        def handle_scheduled_event(event):
            try:
                admin_id = event.data.get(SchedulerConstKeys.ADMIN_ID)

                if not admin_id:
                    debug_utils.log_and_print("没找到管理员ID，无法启动定时任务", log_level="WARNING")
                    return

                # 调用定时处理器的统一接口
                result = message_processor.schedule.create_task(event.data)

                if result.success:
                    feishu_adapter.sender.send_direct_message(admin_id, result)
                    debug_utils.log_and_print(f"✅ 定时任务消息已发送: {event.data.get(SchedulerConstKeys.SCHEDULER_TYPE)}", log_level="INFO")
                else:
                    debug_utils.log_and_print(f"❌ 消息生成失败: {result.error_message}", log_level="ERROR")

            except Exception as e:
                debug_utils.log_and_print(f"处理定时任务事件失败: {e}", log_level="ERROR")

        scheduler_service.add_event_listener(handle_scheduled_event)

    # 配置定时任务
    setup_scheduled_tasks(app_controller)

    return app_controller, feishu_adapter


@require_service(ServiceNames.SCHEDULER, "调度器服务不可用，跳过定时任务配置")
@require_service(ServiceNames.CONFIG, "配置服务不可用，跳过定时任务配置")
def setup_scheduled_tasks(app_controller):
    """配置定时任务（基于配置文件）"""
    scheduler_service = app_controller.get_service(ServiceNames.SCHEDULER)
    config_service = app_controller.get_service(ServiceNames.CONFIG)

    scheduler_config = config_service.get("scheduler", {})
    tasks_config = scheduler_config.get("tasks", [])

    tasks_configured = 0

    for task_config in tasks_config:
        if not task_config.get("enabled", True):
            continue

        task_name = task_config["name"]
        task_type = task_config["type"]
        time_str = task_config["time"]
        task_params = task_config.get("params", {})
        task_debug = task_config.get("debug", {})

        # 处理单任务调试模式：force_latest_time
        if task_debug.get("force_latest_time", False):
            offset_seconds = task_debug.get("force_offset_seconds", 5)
            time_str = _get_debug_time(offset_seconds)
            debug_utils.log_and_print(f"🔧 调试模式：{task_name} 时间调整为 {time_str}", log_level="INFO")

        # 根据任务类型选择触发函数
        task_func = _get_task_function(scheduler_service, task_type)
        if not task_func:
            debug_utils.log_and_print(f"❌ 未知的任务类型: {task_type}", log_level="WARNING")
            continue

        success = scheduler_service.add_daily_task(
            task_name=task_name,
            time_str=time_str,
            task_func=task_func,
            **task_params
        )
        if success:
            tasks_configured += 1

    print(f"✅ 定时任务配置完成，共 {tasks_configured} 个任务")

def _get_debug_time(offset_seconds: int = 5) -> str:
    """获取调试时间：当前时间 + offset_seconds（精确到秒）"""
    debug_time = datetime.now() + timedelta(seconds=offset_seconds)
    return debug_time.strftime("%H:%M:%S")

def _get_task_function(scheduler_service, task_type: str):
    """根据任务类型获取对应的触发函数"""
    task_functions = {
        "daily_schedule": scheduler_service.trigger_daily_schedule_reminder,
        "bilibili_updates": scheduler_service.trigger_bilibili_updates_reminder,
    }
    return task_functions.get(task_type)


def check_system_status(app_controller):
    """检查系统状态（增强版，包含图像服务认证状态）"""
    try:
        health_status = app_controller.health_check()
        overall_status = health_status['overall_status']

        if overall_status == 'healthy':
            print("✅ 系统状态正常")
        else:
            print(f"⚠️ 系统状态: {overall_status}")
            # 仅在异常时显示详细信息
            for service_name, service_info in health_status['services'].items():
                if service_info['status'] != 'healthy':
                    print(f"  - {service_name}: {service_info['status']}")

        # 特别检查图像服务的认证状态
        image_service = app_controller.get_service(ServiceNames.IMAGE)
        if image_service and image_service.is_available():
            try:
                auth_status = image_service.get_auth_status()
                if "error" not in auth_status:
                    if auth_status.get("is_expired", True):
                        print("⚠️ 图像服务认证状态: 令牌已过期")
                    elif auth_status.get("hours_remaining", 0) < 24:
                        hours = auth_status.get("hours_remaining", 0)
                        print(f"⏰ 图像服务认证状态: 令牌还有 {hours:.1f} 小时过期")
                    else:
                        print("✅ 图像服务认证状态: 正常")
                else:
                    print("❌ 图像服务认证状态: 无法获取")
            except Exception as e:
                debug_utils.log_and_print(f"检查图像服务认证状态失败: {e}", log_level="DEBUG")
        elif image_service:
            print("❌ 图像服务: 不可用")

    except Exception as e:
        debug_utils.log_and_print(f"系统状态检查失败: {e}", log_level="ERROR")


@require_service(ServiceNames.SCHEDULER, "调度器服务不可用，无法启动调度循环")
def run_scheduler_loop(app_controller):
    """运行调度器主循环"""
    scheduler_service = app_controller.get_service(ServiceNames.SCHEDULER)

    try:
        while True:
            scheduler_service.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        debug_utils.log_and_print(f"定时任务调度器异常: {e}", log_level="ERROR")


def main():
    """主启动函数"""
    parser = argparse.ArgumentParser(description='飞书机器人')
    parser.add_argument('--verify-api', action='store_true', help='启动时验证API接口')
    parser.add_argument('--http-api', action='store_true', help='启动HTTP API服务器')
    parser.add_argument('--http-port', type=int, default=8000, help='HTTP API端口')

    args = parser.parse_args()

    try:
        # 设置应用
        app_controller, feishu_adapter = setup_application()

        # API验证
        if args.verify_api:
            try:
                from test_runtime_api import validate_with_shared_controller
                validate_with_shared_controller(app_controller)
                print("✅ API验证完成")
            except ImportError:
                debug_utils.log_and_print("❌ 无法导入API验证模块", log_level="WARNING")

        # 系统状态检查
        check_system_status(app_controller)

        # HTTP API服务器
        if args.http_api:
            def start_http_api():
                try:
                    from http_api_server import start_http_server
                    start_http_server(
                        shared_controller=app_controller,
                        host="127.0.0.1", port=args.http_port)
                except ImportError:
                    debug_utils.log_and_print("❌ 无法导入HTTP API服务器模块", log_level="ERROR")
                except Exception as e:
                    debug_utils.log_and_print(f"❌ HTTP API服务器启动失败: {e}", log_level="ERROR")

            http_thread = threading.Thread(target=start_http_api, daemon=True)
            http_thread.start()
            print(f"🌐 HTTP API服务器已启动: http://127.0.0.1:{args.http_port}")

        print("🚀 飞书机器人服务启动完成")
        print("   输入'帮助'查看功能指令")

        # 启动定时任务调度器
        scheduler_thread = threading.Thread(
            target=run_scheduler_loop,
            args=(app_controller,),
            daemon=True,
            name="SchedulerThread"
        )
        scheduler_thread.start()

        print("服务运行中，按 Ctrl+C 停止")

        # 启动飞书适配器（阻塞）
        feishu_adapter.start()

    except KeyboardInterrupt:
        print("\n正在停止服务...")
    except Exception as e:
        debug_utils.log_and_print(f"启动失败: {e}", log_level="ERROR")
        import traceback
        traceback.print_exc()
    finally:
        if 'feishu_adapter' in locals():
            feishu_adapter.stop()
        print("🔴 飞书机器人服务已停止")


async def main_async():
    """异步版本入口（用于Jupyter环境）"""
    try:
        app_controller, feishu_adapter = setup_application()
        check_system_status(app_controller)

        print("🚀 飞书机器人服务启动 (异步模式)")

        # 启动定时任务调度器
        scheduler_thread = threading.Thread(
            target=run_scheduler_loop,
            args=(app_controller,),
            daemon=True,
            name="SchedulerThread"
        )
        scheduler_thread.start()

        # 异步启动
        await feishu_adapter.start_async()

        # 保持运行
        try:
            while True:
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n程序被中断")

    except Exception as e:
        debug_utils.log_and_print(f"程序启动失败: {e}", log_level="ERROR")
    finally:
        if 'feishu_adapter' in locals():
            feishu_adapter.stop()
        print("🔴 飞书机器人服务已停止")


if __name__ == "__main__":
    main()
