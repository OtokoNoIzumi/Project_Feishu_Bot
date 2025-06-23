"""
运行时API验证脚本

在主程序(main_refactored_schedule.py)运行时验证API接口的可用性
支持多种验证方式：共享实例、独立实例、HTTP接口(可选)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from Module.Services.constants import SchedulerTaskTypes
from Module.Application.app_controller import AppController
from Module.Application.app_api_controller import AppApiController


class RuntimeAPIValidator:
    """运行时API验证器"""

    def __init__(self, shared_controller=None):
        """
        初始化验证器

        Args:
            shared_controller: 可选的共享AppController实例
        """
        if shared_controller:
            print("🔗 使用共享的AppController实例")
            self.app_controller = shared_controller
            self.app_api_controller = AppApiController(self.app_controller)
            self.is_shared = True
        else:
            print("🆕 创建独立的AppController实例")
            self._init_independent_controller()
            self.is_shared = False

    def _init_independent_controller(self):
        """初始化独立的控制器实例"""
        # 加载环境变量
        load_dotenv(os.path.join(current_dir, ".env"))

        # 创建独立的AppController
        self.app_controller = AppController(project_root_path=str(current_dir))
        self.app_api_controller = AppApiController(self.app_controller)

        # 注册服务
        registration_results = self.app_controller.auto_register_services()
        success_count = sum(1 for success in registration_results.values() if success)
        total_count = len(registration_results)
        print(f"📦 独立实例服务注册: {success_count}/{total_count}")

    def validate_all_apis(self):
        """验证所有API接口"""
        print("\n🧪 开始运行时API验证")
        print("=" * 50)

        results = {}

        # 1. 健康检查
        results['health'] = self._test_health_api()

        # 2. 日程API
        results['schedule'] = self._test_schedule_api()

        # 3. B站API
        results['bilibili'] = self._test_bilibili_api()

        # 4. 音频API
        results['audio'] = self._test_audio_api()

        # 5. 图像API
        results['image'] = self._test_image_api()

        # 6. 调度器API
        results['scheduler'] = self._test_scheduler_api()

        # 总结结果
        self._summarize_results(results)

        return results

    def _test_health_api(self):
        """测试健康检查API"""
        print("\n🏥 测试健康检查API")
        try:
            result = self.app_controller.health_check()
            status = result['overall_status']
            services = len(result['services'])
            print(f"   ✅ 系统状态: {status}, 服务数: {services}")
            return {"success": True, "status": status, "services": services}
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            return {"success": False, "error": str(e)}

    def _test_schedule_api(self):
        """测试日程API"""
        print("\n📅 测试日程API")
        try:
            result = self.app_api_controller.get_scheduled_tasks()
            if result['success']:
                status = result['status']
                # 只依赖get_status返回的结构
                task_count = status.get('task_count', 0)
                service_status = status.get('status', 'unknown')
                tasks = status.get('tasks', [])
                events_count = len(tasks) if isinstance(tasks, list) else 0
                print(f"   ✅ 调度器数据: 任务数: {events_count}, 调度器状态: {service_status}")
                return {"success": True, "events": events_count, "scheduler_status": service_status, "task_count": task_count}

            print(f"   ❌ 失败: {result.get('error', 'unknown')}")
            return {"success": False, "error": result.get('error')}

        except Exception as e:
            print(f"   ❌ 异常: {e}")
            return {"success": False, "error": str(e)}

    def _test_bilibili_api(self):
        """测试B站API"""
        print("\n📺 测试B站API")
        try:
            result = self.app_api_controller.trigger_bilibili_update(['favorites'])
            if result['success']:
                status_code = result.get('status_code', 'unknown')
                print(f"   ✅ B站API调用成功: {status_code}")
                return {"success": True, "status_code": status_code}

            print(f"   ❌ 失败: {result.get('error', 'unknown')}")
            return {"success": False, "error": result.get('error')}

        except Exception as e:
            print(f"   ❌ 异常: {e}")
            return {"success": False, "error": str(e)}

    def _test_audio_api(self):
        """测试音频API"""
        print("\n🎤 测试音频API")
        try:
            result = self.app_api_controller.generate_tts("运行时API测试")
            if result['success']:
                audio_size = len(result['audio_data'])
                print(f"   ✅ TTS生成成功: {audio_size} 字节")
                return {"success": True, "audio_size": audio_size}

            print(f"   ❌ 失败: {result['error']}")
            return {"success": False, "error": result['error']}

        except Exception as e:
            print(f"   ❌ 异常: {e}")
            return {"success": False, "error": str(e)}

    def _test_image_api(self):
        """测试图像API"""
        print("\n🎨 测试图像API")
        try:
            result = self.app_api_controller.generate_image("API测试小猫")
            if result['success']:
                image_count = len(result['image_paths'])
                print(f"   ✅ 图像生成成功: {image_count} 张")
                return {"success": True, "image_count": image_count}

            print(f"   ❌ 失败: {result['error']}")
            return {"success": False, "error": result['error']}

        except Exception as e:
            print(f"   ❌ 异常: {e}")
            return {"success": False, "error": str(e)}

    def _test_scheduler_api(self):
        """测试调度器API"""
        print("\n⏰ 测试调度器API")
        try:
            # 获取任务列表
            result = self.app_api_controller.get_scheduled_tasks()
            if result['success']:
                task_count = len(result['status']['tasks'])
                print(f"   ✅ 获取任务列表: {task_count} 个任务")

                # 测试添加临时任务
                add_result = self.app_api_controller.add_scheduled_task(
                    "runtime_test_task", "23:59", SchedulerTaskTypes.DAILY_SCHEDULE
                )
                if add_result['success']:
                    print("   ✅ 添加测试任务成功")

                    # 立即删除测试任务
                    remove_result = self.app_api_controller.remove_scheduled_task("runtime_test_task")
                    if remove_result['success']:
                        print("   ✅ 删除测试任务成功")

                return {"success": True, "original_tasks": task_count}

            print(f"   ❌ 失败: {result['error']}")
            return {"success": False, "error": result['error']}

        except Exception as e:
            print(f"   ❌ 异常: {e}")
            return {"success": False, "error": str(e)}

    def _summarize_results(self, results):
        """总结测试结果"""
        print("\n" + "=" * 50)
        print("📊 运行时API验证结果:")

        success_count = 0
        total_count = len(results)

        for api_name, result in results.items():
            if result.get('success', False):
                print(f"   ✅ {api_name}: 正常")
                success_count += 1
            else:
                print(f"   ❌ {api_name}: 异常")

        print(f"\n🎯 总体结果: {success_count}/{total_count} API正常")

        if success_count == total_count:
            print("🎉 所有API在运行时均可正常访问！")
        else:
            print("⚠️ 部分API存在问题，建议检查服务状态")

        print(f"💡 验证方式: {'共享实例' if self.is_shared else '独立实例'}")

    def start_interactive_mode(self):
        """启动交互模式"""
        print("\n🎮 进入交互模式 (输入 'help' 查看命令)")

        while True:
            try:
                command = input("\n> ").strip().lower()
                match command:
                    case 'help':
                        self._show_interactive_help()
                    case 'quit' | 'exit':
                        print("👋 退出交互模式")
                        break
                    case 'health':
                        self._test_health_api()
                    case 'schedule':
                        self._test_schedule_api()
                    case 'bili':
                        self._test_bilibili_api()
                    case 'audio':
                        self._test_audio_api()
                    case 'image':
                        self._test_image_api()
                    case 'scheduler':
                        self._test_scheduler_api()
                    case 'all':
                        self.validate_all_apis()
                    case _:
                        print(f"❓ 未知命令: {command}")

            except KeyboardInterrupt:
                print("\n👋 退出交互模式")
                break
            except Exception as e:
                print(f"❌ 执行错误: {e}")

    def _show_interactive_help(self):
        """显示交互模式帮助"""
        print("""
🎮 交互模式命令:
   help      - 显示此帮助
   all       - 运行所有API测试
   health    - 测试健康检查API
   schedule  - 测试日程API
   bili      - 测试B站API
   audio     - 测试音频API
   image     - 测试图像API
   scheduler - 测试调度器API
   quit/exit - 退出交互模式
        """)


def main_independent():
    """独立验证模式"""
    print("🚀 运行时API验证 - 独立模式")

    validator = RuntimeAPIValidator()

    # 选择验证方式
    print("\n选择验证方式:")
    print("1. 一次性验证所有API")
    print("2. 交互模式验证")

    choice = input("请选择 (1/2): ").strip()

    if choice == '1':
        validator.validate_all_apis()
    elif choice == '2':
        validator.start_interactive_mode()
    else:
        print("无效选择，执行一次性验证")
        validator.validate_all_apis()


def validate_with_shared_controller(shared_controller):
    """使用共享控制器进行验证"""
    print("🚀 运行时API验证 - 共享模式")

    validator = RuntimeAPIValidator(shared_controller)
    return validator.validate_all_apis()


if __name__ == "__main__":
    main_independent()
