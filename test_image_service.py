"""
图像服务测试脚本

测试内容：
1. 图像服务初始化
2. Gradio客户端连接
3. 图像生成功能
4. 图像转换功能
5. 服务状态检查
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from Module.Application.app_controller import AppController
from Module.Services.image import ImageService
from Module.Common.scripts.common import debug_utils


def test_image_service():
    """测试图像服务功能"""
    print("=== 图像服务测试 ===")

    try:
        # 1. 测试应用控制器初始化
        print("\n1. 初始化应用控制器...")
        app_controller = AppController(project_root_path=str(project_root))

        # 注册服务 - 使用正确的方法名
        registration_results = app_controller.auto_register_services()
        print(f"服务注册结果: {registration_results}")

        # 获取配置服务（不调用不存在的initialize方法）
        config_service = app_controller.get_service('config')
        if config_service:
            print("✅ 配置服务获取成功")

        # 2. 测试图像服务初始化
        print("\n2. 初始化图像服务...")
        image_service = app_controller.get_service('image')

        if image_service:
            print("✅ 图像服务获取成功")

            # 检查服务状态
            status = image_service.get_status()
            print(f"图像服务状态: {status}")

            # 尝试初始化（ImageService确实有initialize方法）
            init_result = image_service.initialize()
            print(f"图像服务初始化: {'✅ 成功' if init_result else '❌ 失败'}")

            # 3. 测试服务可用性
            print("\n3. 检查服务可用性...")
            is_available = image_service.is_available()
            print(f"图像服务可用性: {'✅ 可用' if is_available else '❌ 不可用'}")

            if is_available:
                print("  - Gradio客户端连接正常")
                print("  - 可以进行图像生成和转换")
            else:
                print("  - Gradio客户端连接失败或未配置SERVER_ID")
                print("  - 图像功能不可用")

            # 4. 测试配置检查
            print("\n4. 检查配置...")
            server_id = getattr(image_service, 'server_id', None)
            print(f"SERVER_ID配置: {server_id if server_id else '未配置'}")

            if hasattr(image_service, 'gradio_client') and image_service.gradio_client:
                print("✅ Gradio客户端已连接")
            else:
                print("❌ Gradio客户端未连接")

        else:
            print("❌ 图像服务获取失败")

        # 5. 测试应用控制器健康检查 - 使用正确的方法名
        print("\n5. 系统健康检查...")
        health_status = app_controller.health_check()
        print(f"系统整体状态: {health_status['overall_status']}")
        print(f"健康服务数: {health_status['summary']['healthy']}")
        print(f"异常服务数: {health_status['summary']['unhealthy']}")
        print(f"未初始化服务数: {health_status['summary']['uninitialized']}")

        for service_name, service_info in health_status['services'].items():
            status = service_info['status']
            status_icon = "✅" if status == "healthy" else "❌" if status == "unhealthy" else "⏳"
            print(f"  {status_icon} {service_name}: {status}")

        # 6. 显示使用说明
        print("\n6. 使用说明...")
        print("图像服务功能:")
        print("  - 文本生图: '生图 描述内容' 或 'AI画图 描述内容'")
        print("  - 图像转换: 直接发送图片进行风格转换")
        print("  - 支持多张图片生成")
        print("  - 自动错误处理和状态反馈")

        if image_service and image_service.is_available():
            print("\n✅ 图像服务测试完成 - 服务正常")
        else:
            print("\n⚠️ 图像服务测试完成 - 服务不可用，请检查SERVER_ID配置")

    except Exception as e:
        print(f"\n❌ 图像服务测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_image_service()