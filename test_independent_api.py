"""
独立API测试脚本

展示如何在不依赖飞书前端的情况下访问系统的核心功能
这个脚本模拟了其他前端（Web、移动端、第三方系统）如何调用API
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from Module.Application.app_controller import AppController


class IndependentAPIClient:
    """独立API客户端 - 模拟其他前端的调用方式"""

    def __init__(self):
        """初始化API客户端"""
        # 加载环境变量
        load_dotenv(os.path.join(current_dir, ".env"))

        # 创建应用控制器
        self.app_controller = AppController(project_root_path=str(current_dir))

        # 注册服务
        print("🔧 初始化服务...")
        registration_results = self.app_controller.auto_register_services()

        success_count = sum(1 for success in registration_results.values() if success)
        total_count = len(registration_results)
        print(f"✅ 服务注册完成: {success_count}/{total_count}")

        # 初始化图像服务
        image_service = self.app_controller.get_service('image')
        if image_service:
            image_service.initialize()
            print("✅ 图像服务初始化完成")

    def test_health_check(self):
        """测试健康检查API"""
        print("\n=== 健康检查API测试 ===")
        result = self.app_controller.health_check()
        print(f"系统状态: {result['overall_status']}")
        print(f"服务统计: {result['summary']}")
        return result

    def test_schedule_api(self):
        """测试日程相关API"""
        print("\n=== 日程API测试 ===")

        # 获取日程数据
        print("1. 获取日程数据:")
        result = self.app_controller.api_get_schedule_data()
        print(f"   结果: {result['success']}")
        if result['success']:
            data = result['data']
            print(f"   日期: {data['date']} {data['weekday']}")
            print(f"   事件数: {len(data['events'])}")
            for event in data['events']:
                print(f"     - {event['time']} {event['title']}")

        return result

    def test_bilibili_api(self):
        """测试B站相关API"""
        print("\n=== B站API测试 ===")

        # 触发B站更新检查
        print("1. 触发B站更新检查:")
        result = self.app_controller.api_trigger_bilibili_update(sources=["favorites"])
        print(f"   结果: {result['success']}")
        if result['success']:
            print(f"   状态码: {result.get('status_code')}")
            print(f"   数据源: {result.get('sources')}")
        else:
            print(f"   错误: {result.get('error')}")

        return result

    def test_audio_api(self):
        """测试音频API"""
        print("\n=== 音频API测试 ===")

        # 生成TTS音频
        print("1. 生成TTS音频:")
        test_text = "这是一个API测试音频"
        result = self.app_controller.api_generate_tts(test_text)
        print(f"   结果: {result['success']}")
        if result['success']:
            audio_data = result['audio_data']
            print(f"   音频大小: {len(audio_data)} 字节")
            print(f"   文本: {result['text']}")
        else:
            print(f"   错误: {result['error']}")

        return result

    def test_image_api(self):
        """测试图像API"""
        print("\n=== 图像API测试 ===")

        # 生成AI图像
        print("1. 生成AI图像:")
        test_prompt = "一只可爱的小猫在花园里"
        result = self.app_controller.api_generate_image(test_prompt)
        print(f"   结果: {result['success']}")
        if result['success']:
            image_paths = result['image_paths']
            print(f"   生成图片数: {len(image_paths)}")
            print(f"   提示词: {result['prompt']}")
            for i, path in enumerate(image_paths):
                print(f"     图片{i+1}: {path}")
        else:
            print(f"   错误: {result['error']}")

        return result

    def test_scheduler_api(self):
        """测试调度器API"""
        print("\n=== 调度器API测试 ===")

        # 获取定时任务列表
        print("1. 获取定时任务列表:")
        result = self.app_controller.api_get_scheduled_tasks()
        print(f"   结果: {result['success']}")
        if result['success']:
            tasks = result['tasks']
            status = result['status']
            print(f"   任务总数: {status['task_count']}")
            print(f"   事件监听器: {status['event_listeners']}")

            if tasks:
                print("   任务列表:")
                for task in tasks:
                    print(f"     - {task['name']} | {task.get('time', 'N/A')} | {task.get('function_name', 'N/A')}")
            else:
                print("   无定时任务")

        # 添加测试任务
        print("\n2. 添加测试任务:")
        result = self.app_controller.api_add_scheduled_task(
            task_name="api_test_task",
            time_str="23:59",
            task_type="daily_schedule"
        )
        print(f"   结果: {result['success']}")
        print(f"   消息: {result['message']}")

        # 移除测试任务
        print("\n3. 移除测试任务:")
        result = self.app_controller.api_remove_scheduled_task("api_test_task")
        print(f"   结果: {result['success']}")
        print(f"   消息: {result['message']}")

        return result

    def run_full_test(self):
        """运行完整的API测试"""
        print("🚀 独立API测试开始\n")
        print("=" * 50)

        results = {}

        # 运行各项测试
        results['health'] = self.test_health_check()
        results['schedule'] = self.test_schedule_api()
        results['bilibili'] = self.test_bilibili_api()
        results['audio'] = self.test_audio_api()
        results['image'] = self.test_image_api()
        results['scheduler'] = self.test_scheduler_api()

        # 总结测试结果
        print("\n" + "=" * 50)
        print("🎯 测试结果总结:")

        success_count = 0
        total_count = len(results)

        for test_name, result in results.items():
            if isinstance(result, dict) and result.get('success', False):
                print(f"   ✅ {test_name}: 成功")
                success_count += 1
            else:
                print(f"   ❌ {test_name}: 失败")

        print(f"\n📊 总体结果: {success_count}/{total_count} 测试通过")

        if success_count == total_count:
            print("🎉 所有API测试通过！系统可以独立为其他前端提供服务")
        else:
            print("⚠️ 部分API测试失败，请检查服务配置")

        return results


def main():
    """主函数"""
    try:
        # 创建API客户端
        client = IndependentAPIClient()

        # 运行测试
        results = client.run_full_test()

        print("\n" + "=" * 50)
        print("📋 使用说明:")
        print("1. 其他前端可以通过创建AppController实例访问所有API")
        print("2. 所有API方法以'api_'开头，返回标准的JSON格式")
        print("3. 支持的前端类型：Web应用、移动端、CLI工具、第三方集成")
        print("4. API完全独立于飞书，可以同时支持多种前端")

        return results

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()