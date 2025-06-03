"""
飞书机器人重构版 - 阶段3 MVP (音频+图像+定时任务)

该启动文件实现了：
1. 音频处理功能 (TTS语音合成)
2. 图像处理功能 (AI图像生成、图像风格转换)
3. 定时任务功能 (日程提醒、B站更新推送)
4. 四层架构的完整实现
5. 统一的服务管理和健康检查

架构设计：
- 前端交互层: FeishuAdapter - 飞书协议转换、媒体上传、异步处理
- 核心业务层: MessageProcessor - 指令识别、异步任务调度、定时消息处理
- 应用控制层: AppController - 服务注册、统一调用管理
- 服务层: AudioService, ImageService, SchedulerService, ConfigService, CacheService
"""

import os
import sys
import asyncio
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
import argparse

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from Module.Application.app_controller import AppController
from Module.Business.message_processor import MessageProcessor
from Module.Adapters.feishu_adapter import FeishuAdapter
from Module.Common.scripts.common import debug_utils


def setup_application():
    """设置应用组件"""
    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    debug_utils.log_and_print("current_dir", current_dir, log_level="INFO")
    debug_utils.log_and_print("=== 飞书机器人重构版启动 ===", log_level="INFO")
    debug_utils.log_and_print("当前版本：阶段3 MVP - 音频+图像+定时任务", log_level="INFO")

    # 1. 创建应用控制器
    app_controller = AppController(project_root_path=str(current_dir))

    # 2. 自动注册所有可用服务
    debug_utils.log_and_print("正在注册服务...", log_level="INFO")
    registration_results = app_controller.auto_register_services()

    # 显示注册结果
    success_count = sum(1 for success in registration_results.values() if success)
    total_count = len(registration_results)
    debug_utils.log_and_print(f"自动注册完成，成功: {success_count}/{total_count}", log_level="INFO")

    for service_name, success in registration_results.items():
        status = "✅ 成功" if success else "❌ 失败"
        debug_utils.log_and_print(f"  - {service_name}: {status}", log_level="INFO")

    # 3. 初始化有initialize方法的服务
    image_service = app_controller.get_service('image')
    if image_service:
        image_service.initialize()
        debug_utils.log_and_print("✅ ImageService 初始化完成", log_level="INFO")

    # 4. 创建消息处理器
    message_processor = MessageProcessor(app_controller=app_controller)

    # 5. 创建飞书适配器
    feishu_adapter = FeishuAdapter(
        message_processor=message_processor,
        app_controller=app_controller
    )

    # 6. 建立事件监听机制（解耦的方式）
    scheduler_service = app_controller.get_service('scheduler')
    if scheduler_service:
        # 添加事件监听器，让FeishuAdapter监听定时任务事件
        def handle_scheduled_event(event):
            """处理定时任务事件"""
            try:
                debug_utils.log_and_print(f"收到定时任务事件: {event.event_type}", log_level="INFO")

                admin_id = event.data.get('admin_id')
                message_type = event.data.get('message_type')

                if not admin_id:
                    debug_utils.log_and_print("事件中缺少admin_id，跳过处理", log_level="WARNING")
                    return

                # 通过MessageProcessor生成消息内容
                if message_type == "daily_schedule":
                    result = message_processor.create_scheduled_message("daily_schedule")
                elif message_type == "bilibili_updates":
                    sources = event.data.get('sources')
                    result = message_processor.create_scheduled_message("bilibili_updates", sources=sources)
                else:
                    debug_utils.log_and_print(f"未知的消息类型: {message_type}", log_level="WARNING")
                    return

                if result.success:
                    # 发送消息
                    feishu_adapter._send_direct_message(admin_id, result)
                    debug_utils.log_and_print(f"✅ 定时消息已发送: {message_type}", log_level="INFO")
                else:
                    debug_utils.log_and_print(f"❌ 消息生成失败: {result.error_message}", log_level="ERROR")

            except Exception as e:
                debug_utils.log_and_print(f"处理定时任务事件失败: {e}", log_level="ERROR")

        scheduler_service.add_event_listener(handle_scheduled_event)
        debug_utils.log_and_print("✅ 定时任务事件监听已建立", log_level="INFO")

    # 7. 配置定时任务
    setup_scheduled_tasks(app_controller)

    return app_controller, feishu_adapter


def setup_scheduled_tasks(app_controller):
    """配置定时任务"""
    debug_utils.log_and_print("正在配置定时任务...", log_level="INFO")

    # 获取调度器服务
    scheduler_service = app_controller.get_service('scheduler')
    if not scheduler_service:
        debug_utils.log_and_print("❌ 调度器服务不可用，跳过定时任务配置", log_level="WARNING")
        return

    # 配置定时任务
    tasks_configured = 0

    # 任务1: 每天07:30发送日程提醒
    success = scheduler_service.add_daily_task(
        task_name="daily_schedule_reminder",
        time_str="06:26",
        task_func=scheduler_service.trigger_daily_schedule_reminder
    )
    if success:
        tasks_configured += 1
        debug_utils.log_and_print("✅ 日程提醒任务已配置 (07:30)", log_level="INFO")

    # 任务2: 每天15:30发送B站更新（不指定sources）
    success = scheduler_service.add_daily_task(
        task_name="bili_updates_afternoon",
        time_str="15:30",
        task_func=scheduler_service.trigger_bilibili_updates_reminder
    )
    if success:
        tasks_configured += 1
        debug_utils.log_and_print("✅ B站更新任务已配置 (15:30)", log_level="INFO")

    # 任务3: 每天23:55发送B站更新（指定sources）
    success = scheduler_service.add_daily_task(
        task_name="bili_updates_night",
        time_str="23:55",
        task_func=scheduler_service.trigger_bilibili_updates_reminder,
        sources=["favorites", "dynamic"]
    )
    if success:
        tasks_configured += 1
        debug_utils.log_and_print("✅ B站夜间更新任务已配置 (23:55)", log_level="INFO")

    debug_utils.log_and_print(f"定时任务配置完成，共配置 {tasks_configured} 个任务", log_level="INFO")


def display_system_status(app_controller):
    """显示系统状态"""
    debug_utils.log_and_print("\n=== 系统状态检查 ===", log_level="INFO")

    # 健康检查
    health_status = app_controller.health_check()
    debug_utils.log_and_print(f"系统状态: {health_status['overall_status']}", log_level="INFO")
    debug_utils.log_and_print(
        f"服务统计: {health_status['summary']['healthy']}健康 / "
        f"{health_status['summary']['unhealthy']}异常 / "
        f"{health_status['summary']['uninitialized']}未初始化",
        log_level="INFO"
    )

    # 显示各服务状态
    for service_name, service_info in health_status['services'].items():
        status = service_info['status']
        status_icon = {
            'healthy': '✅',
            'unhealthy': '⚠️',
            'uninitialized': '⏳',
            'error': '❌'
        }.get(status, '❓')

        debug_utils.log_and_print(f"  {status_icon} {service_name}: {status}", log_level="INFO")

        # 显示服务详细信息
        if service_info.get('details') and service_info['details'].get('details'):
            details = service_info['details']['details']
            if service_name == 'audio':
                ffmpeg_status = "✅" if details.get('ffmpeg_available') else "❌"
                tts_status = "✅" if details.get('tts_available') else "❌"
                debug_utils.log_and_print(f"    - FFmpeg: {ffmpeg_status}", log_level="INFO")
                debug_utils.log_and_print(f"    - TTS服务: {tts_status}", log_level="INFO")
            elif service_name == 'image':
                gradio_status = "✅" if details.get('gradio_connected') else "❌"
                server_id_status = "✅" if details.get('server_id_configured') else "❌"
                debug_utils.log_and_print(f"    - Gradio连接: {gradio_status}", log_level="INFO")
                debug_utils.log_and_print(f"    - SERVER_ID配置: {server_id_status}", log_level="INFO")
            elif service_name == 'scheduler':
                task_count = details.get('total_tasks', 0)
                scheduler_active = "✅" if details.get('scheduler_active') else "❌"
                debug_utils.log_and_print(f"    - 调度器状态: {scheduler_active}", log_level="INFO")
                debug_utils.log_and_print(f"    - 任务数量: {task_count}", log_level="INFO")

    debug_utils.log_and_print("===================\n", log_level="INFO")


def display_scheduled_tasks(app_controller):
    """显示定时任务列表"""
    debug_utils.log_and_print("=== 定时任务列表 ===", log_level="INFO")

    scheduler_service = app_controller.get_service('scheduler')
    if not scheduler_service:
        debug_utils.log_and_print("调度器服务不可用", log_level="WARNING")
        return

    tasks = scheduler_service.list_tasks()
    if not tasks:
        debug_utils.log_and_print("未配置任何定时任务", log_level="INFO")
        return

    for task in tasks:
        task_name = task.get('name', '未知任务')
        next_run = task.get('next_run', '未知')
        time_config = task.get('time', '未配置')
        func_name = task.get('function_name', '未知函数')

        debug_utils.log_and_print(
            f"📅 {task_name} | ⏰ {time_config} | 🚀 {func_name} | ⏭️ {next_run}",
            log_level="INFO"
        )

    debug_utils.log_and_print("===================\n", log_level="INFO")


def run_scheduler_loop(app_controller):
    """运行调度器主循环"""
    debug_utils.log_and_print("🕒 启动定时任务调度器...", log_level="INFO")

    scheduler_service = app_controller.get_service('scheduler')
    if not scheduler_service:
        debug_utils.log_and_print("❌ 调度器服务不可用，无法启动定时任务", log_level="ERROR")
        return

    try:
        while True:
            scheduler_service.run_pending()
            time.sleep(1)  # 降低CPU占用
    except KeyboardInterrupt:
        debug_utils.log_and_print("定时任务调度器被用户中断", log_level="INFO")
    except Exception as e:
        debug_utils.log_and_print(f"定时任务调度器异常: {e}", log_level="ERROR")


def main():
    """主启动函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='飞书机器人重构版')
    parser.add_argument('--verify-api', action='store_true', help='启动时验证API接口')
    parser.add_argument('--http-api', action='store_true', help='同时启动HTTP API服务器')
    parser.add_argument('--http-port', type=int, default=8000, help='HTTP API服务器端口')

    args = parser.parse_args()

    try:
        # 设置应用
        app_controller, feishu_adapter = setup_application()

        # 可选：验证API接口
        if args.verify_api:
            debug_utils.log_and_print("\n🧪 启动时API验证", log_level="INFO")
            try:
                from test_runtime_api import validate_with_shared_controller
                validate_with_shared_controller(app_controller)
            except ImportError:
                debug_utils.log_and_print("❌ 无法导入API验证模块", log_level="WARNING")

        # 显示系统状态
        display_system_status(app_controller)

        # 显示定时任务列表
        display_scheduled_tasks(app_controller)

        # 可选：启动HTTP API服务器
        if args.http_api:
            debug_utils.log_and_print(f"🌐 启动HTTP API服务器 (端口: {args.http_port})", log_level="INFO")

            def start_http_api():
                try:
                    from http_api_server import start_http_server
                    start_http_server(shared_controller=app_controller,
                                    host="127.0.0.1",
                                    port=args.http_port)
                except ImportError:
                    debug_utils.log_and_print("❌ 无法导入HTTP API服务器模块", log_level="ERROR")
                except Exception as e:
                    debug_utils.log_and_print(f"❌ HTTP API服务器启动失败: {e}", log_level="ERROR")

            http_thread = threading.Thread(target=start_http_api, daemon=True)
            http_thread.start()
            debug_utils.log_and_print(f"✅ HTTP API服务器已在后台启动: http://127.0.0.1:{args.http_port}", log_level="INFO")
            debug_utils.log_and_print(f"📚 API文档地址: http://127.0.0.1:{args.http_port}/docs", log_level="INFO")

        # 显示功能特性
        debug_utils.log_and_print("🚀 启动飞书机器人服务...", log_level="INFO")
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  🎨 AI图像生成 (输入'生图 描述内容')", log_level="INFO")
        debug_utils.log_and_print("  🖼️ 图像风格转换 (直接发送图片)", log_level="INFO")
        debug_utils.log_and_print("  📋 菜单和卡片交互", log_level="INFO")
        debug_utils.log_and_print("  ⏰ 定时任务 (日程提醒、B站更新)", log_level="INFO")
        debug_utils.log_and_print("  ❓ 帮助功能 (输入'帮助')", log_level="INFO")

        if args.http_api:
            debug_utils.log_and_print("  🌐 HTTP API接口 (外部调用)", log_level="INFO")

        # 启动定时任务调度器（在后台线程中运行）
        scheduler_thread = threading.Thread(
            target=run_scheduler_loop,
            args=(app_controller,),
            daemon=True,
            name="SchedulerThread"
        )
        scheduler_thread.start()
        debug_utils.log_and_print("✅ 定时任务调度器已在后台启动", log_level="INFO")

        debug_utils.log_and_print("服务已启动，按 Ctrl+C 停止", log_level="INFO")

        # 显示使用提示
        if args.verify_api or args.http_api:
            debug_utils.log_and_print("\n💡 使用提示:", log_level="INFO")
            if args.verify_api:
                debug_utils.log_and_print("  - API验证已完成，所有接口可用", log_level="INFO")
            if args.http_api:
                debug_utils.log_and_print(f"  - HTTP API已启动，可通过 http://127.0.0.1:{args.http_port} 访问", log_level="INFO")
                debug_utils.log_and_print("  - 其他应用可通过HTTP接口调用所有功能", log_level="INFO")

        # 启动适配器（阻塞）
        feishu_adapter.start()

    except KeyboardInterrupt:
        debug_utils.log_and_print("\n收到停止信号，正在关闭服务...", log_level="INFO")
    except Exception as e:
        debug_utils.log_and_print(f"启动失败: {e}", log_level="ERROR")
        import traceback
        traceback.print_exc()
    finally:
        debug_utils.log_and_print("正在停止服务...", log_level="INFO")
        if 'feishu_adapter' in locals():
            feishu_adapter.stop()
        debug_utils.log_and_print("🔴 飞书机器人服务已停止", log_level="INFO")


async def main_async():
    """异步版本的主入口（用于Jupyter等环境）"""
    try:
        # 设置应用
        app_controller, feishu_adapter = setup_application()

        # 显示系统状态
        display_system_status(app_controller)

        # 显示定时任务列表
        display_scheduled_tasks(app_controller)

        # 启动飞书机器人服务
        debug_utils.log_and_print("🚀 启动飞书机器人服务 (异步模式)...", log_level="INFO")
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  🎨 AI图像生成 (输入'生图 描述内容')", log_level="INFO")
        debug_utils.log_and_print("  🖼️ 图像风格转换 (直接发送图片)", log_level="INFO")
        debug_utils.log_and_print("  📋 菜单和卡片交互", log_level="INFO")
        debug_utils.log_and_print("  ⏰ 定时任务 (日程提醒、B站更新)", log_level="INFO")
        debug_utils.log_and_print("  ❓ 帮助功能 (输入'帮助')", log_level="INFO")

        # 启动定时任务调度器（在后台线程中运行）
        scheduler_thread = threading.Thread(
            target=run_scheduler_loop,
            args=(app_controller,),
            daemon=True,
            name="SchedulerThread"
        )
        scheduler_thread.start()
        debug_utils.log_and_print("✅ 定时任务调度器已在后台启动", log_level="INFO")

        # 异步方式启动
        await feishu_adapter.start_async()

        # 保持运行
        try:
            while True:
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            debug_utils.log_and_print("\n程序被用户中断", log_level="INFO")

    except Exception as e:
        debug_utils.log_and_print(f"程序启动失败: {e}", log_level="ERROR")
    finally:
        debug_utils.log_and_print("正在停止服务...", log_level="INFO")
        if 'feishu_adapter' in locals():
            feishu_adapter.stop()
        debug_utils.log_and_print("🔴 飞书机器人服务已停止", log_level="INFO")


if __name__ == "__main__":
    main()

# Jupyter环境使用示例:
# await main_async()