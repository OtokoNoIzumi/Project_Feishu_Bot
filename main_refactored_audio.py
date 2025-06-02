"""
飞书机器人服务主入口（重构版 - 阶段2A音频处理功能）

该版本实现了完整的音频处理功能，包括TTS语音合成和FFmpeg转换
架构：应用控制器 + 服务层 + 业务层 + 适配器层
"""

import os
import sys
import time
import asyncio
import threading
from dotenv import load_dotenv

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
print('current_dir', current_dir)
# 导入新架构模块
from Module.Application.app_controller import AppController
from Module.Business.message_processor import MessageProcessor
from Module.Adapters.feishu_adapter import FeishuAdapter
from Module.Common.scripts.common import debug_utils


def setup_application():
    """设置应用组件"""
    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    debug_utils.log_and_print("=== 飞书机器人重构版启动 ===", log_level="INFO")
    debug_utils.log_and_print("当前版本：阶段2A MVP - 音频处理功能", log_level="INFO")

    # 1. 创建应用控制器
    app_controller = AppController(project_root_path=current_dir)

    # 2. 自动注册所有可用服务
    debug_utils.log_and_print("正在注册服务...", log_level="INFO")
    register_results = app_controller.auto_register_services()

    # 显示注册结果
    for service_name, success in register_results.items():
        status = "✅ 成功" if success else "❌ 失败"
        debug_utils.log_and_print(f"  - {service_name}: {status}", log_level="INFO")

    # 3. 创建消息处理器
    message_processor = MessageProcessor(app_controller=app_controller)

    # 4. 创建飞书适配器
    feishu_adapter = FeishuAdapter(
        message_processor=message_processor,
        app_controller=app_controller
    )

    return app_controller, feishu_adapter


def display_system_status(app_controller):
    """显示系统状态"""
    debug_utils.log_and_print("\n=== 系统状态检查 ===", log_level="INFO")

    # 健康检查
    health = app_controller.health_check()
    debug_utils.log_and_print(f"系统状态: {health['overall_status']}", log_level="INFO")
    debug_utils.log_and_print(
        f"服务统计: {health['summary']['healthy']}健康 / {health['summary']['unhealthy']}异常 / {health['summary']['uninitialized']}未初始化",
        log_level="INFO"
    )

    # 显示各服务状态
    for service_name, service_info in health['services'].items():
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

    debug_utils.log_and_print("===================\n", log_level="INFO")


def main():
    """程序主入口"""
    try:
        # 设置应用
        app_controller, feishu_adapter = setup_application()

        # 显示系统状态
        display_system_status(app_controller)

        # 启动飞书适配器
        debug_utils.log_and_print("🚀 启动飞书机器人服务...", log_level="INFO")
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  📋 菜单和卡片交互", log_level="INFO")
        debug_utils.log_and_print("  ❓ 帮助功能 (输入'帮助')", log_level="INFO")
        debug_utils.log_and_print("服务已启动，按 Ctrl+C 停止", log_level="INFO")

        # 同步方式启动（阻塞）
        feishu_adapter.start()

    except KeyboardInterrupt:
        debug_utils.log_and_print("\n程序被用户中断", log_level="INFO")
    except Exception as e:
        debug_utils.log_and_print(f"程序启动失败: {e}", log_level="ERROR")
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

        # 启动飞书适配器
        debug_utils.log_and_print("🚀 启动飞书机器人服务 (异步模式)...", log_level="INFO")
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  📋 菜单和卡片交互", log_level="INFO")
        debug_utils.log_and_print("  ❓ 帮助功能 (输入'帮助')", log_level="INFO")

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