"""
音频服务测试脚本

用于验证音频服务的基本功能
"""

import os
import sys
import time
from dotenv import load_dotenv

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from Module.Application.app_controller import AppController
from Module.Common.scripts.common import debug_utils


def test_audio_service():
    """测试音频服务"""
    print("=== 音频服务测试 ===\n")

    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    # 创建应用控制器
    app_controller = AppController(project_root_path=current_dir)

    # 注册服务
    print("1. 注册服务...")
    results = app_controller.auto_register_services()
    for service_name, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {service_name}: {status}")

    # 获取音频服务状态
    print("\n2. 检查音频服务状态...")
    audio_service = app_controller.get_service('audio')

    if audio_service:
        print("   ✅ 音频服务初始化成功")

        # 获取服务状态
        status = audio_service.get_status()
        print(f"   FFmpeg可用: {'✅' if status['ffmpeg_available'] else '❌'}")
        print(f"   FFmpeg路径: {status['ffmpeg_path']}")
        print(f"   TTS可用: {'✅' if status['tts_available'] else '❌'}")

        if status['tts_config']:
            tts_config = status['tts_config']
            print(f"   TTS API: {tts_config['api_base']}")
            print(f"   工作流ID: {tts_config['workflow_id']}")
            print(f"   语音ID: {tts_config['voice_id']}")

        # 测试TTS功能（如果可用）
        if status['tts_available']:
            print("\n3. 测试TTS功能...")
            test_text = "这是一个音频服务测试"

            print(f"   测试文本: {test_text}")
            success, audio_data, error_msg = audio_service.process_tts_request(test_text)

            if success and audio_data:
                print(f"   ✅ TTS生成成功，音频大小: {len(audio_data)} bytes")

                # 测试临时文件创建和清理
                print("\n4. 测试文件管理...")
                temp_path = audio_service.create_temp_audio_file(audio_data)
                print(f"   临时文件路径: {temp_path}")
                print(f"   文件存在: {'✅' if os.path.exists(temp_path) else '❌'}")

                # 测试音频转换（如果FFmpeg可用）
                if status['ffmpeg_available']:
                    print("\n5. 测试音频转换...")
                    opus_path, duration = audio_service.convert_to_opus(temp_path)

                    if opus_path and os.path.exists(opus_path):
                        print(f"   ✅ 转换成功")
                        print(f"   输出路径: {opus_path}")
                        print(f"   音频时长: {duration}ms")

                        # 清理转换后的文件
                        audio_service.cleanup_temp_file(opus_path)
                    else:
                        print("   ❌ 转换失败")
                else:
                    print("\n5. 跳过音频转换测试（FFmpeg不可用）")

                # 清理临时文件
                audio_service.cleanup_temp_file(temp_path)
                print("   ✅ 临时文件已清理")

            else:
                print(f"   ❌ TTS生成失败: {error_msg}")
        else:
            print("\n3. 跳过TTS测试（TTS服务不可用）")
            print("   请检查环境变量配置:")
            print("   - COZE_API_KEY")
            print("   - config.json中的bot_id和coze_bot_url")
    else:
        print("   ❌ 音频服务初始化失败")

    # 系统健康检查
    print("\n6. 系统健康检查...")
    health = app_controller.health_check()
    print(f"   系统状态: {health['overall_status']}")
    print(f"   健康服务: {health['summary']['healthy']}")
    print(f"   异常服务: {health['summary']['unhealthy']}")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_audio_service()