"""
飞书机器人重构版 - 阶段2B MVP (音频与图像处理功能)

该启动文件实现了：
1. 音频处理功能 (TTS语音合成)
2. 图像处理功能 (AI图像生成、图像风格转换)
3. 四层架构的完整实现
4. 统一的服务管理和健康检查

架构设计：
- 前端交互层: FeishuAdapter - 飞书协议转换、媒体上传、异步处理
- 核心业务层: MessageProcessor - 指令识别、异步任务调度
- 应用控制层: AppController - 服务注册、统一调用管理
- 服务层: AudioService, ImageService, ConfigService, CacheService
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

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
    debug_utils.log_and_print("当前版本：阶段2B MVP - 音频与图像处理功能", log_level="INFO")

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

    debug_utils.log_and_print("===================\n", log_level="INFO")


def main():
    """主启动函数"""
    try:
        # 设置应用
        app_controller, feishu_adapter = setup_application()

        # 获取配置服务（ConfigService不需要手动初始化）
        config_service = app_controller.get_service('config')
        if config_service:
            debug_utils.log_and_print("✅ 配置服务获取成功", log_level="INFO")

        # 显示系统状态
        display_system_status(app_controller)

        # 启动飞书机器人服务
        debug_utils.log_and_print("🚀 启动飞书机器人服务...", log_level="INFO")

        # 显示功能特性
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  🎨 AI图像生成 (输入'生图 描述内容')", log_level="INFO")
        debug_utils.log_and_print("  🖼️ 图像风格转换 (直接发送图片)", log_level="INFO")
        debug_utils.log_and_print("  📋 菜单和卡片交互", log_level="INFO")
        debug_utils.log_and_print("  ❓ 帮助功能 (输入'帮助')", log_level="INFO")
        debug_utils.log_and_print("服务已启动，按 Ctrl+C 停止", log_level="INFO")

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

        # 获取配置服务（ConfigService不需要手动初始化）
        config_service = app_controller.get_service('config')
        if config_service:
            debug_utils.log_and_print("✅ 配置服务获取成功", log_level="INFO")

        # 显示系统状态
        display_system_status(app_controller)

        # 启动飞书机器人服务
        debug_utils.log_and_print("🚀 启动飞书机器人服务 (异步模式)...", log_level="INFO")
        debug_utils.log_and_print("支持的功能:", log_level="INFO")
        debug_utils.log_and_print("  📱 基础对话和问候", log_level="INFO")
        debug_utils.log_and_print("  🎤 TTS配音 (输入'配音 文本内容')", log_level="INFO")
        debug_utils.log_and_print("  🎨 AI图像生成 (输入'生图 描述内容')", log_level="INFO")
        debug_utils.log_and_print("  🖼️ 图像风格转换 (直接发送图片)", log_level="INFO")
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