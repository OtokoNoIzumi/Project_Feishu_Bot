"""
SchedulerService 测试脚本

验证定时任务功能和富文本卡片消息生成
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
from Module.Business.message_processor import MessageProcessor
from Module.Common.scripts.common import debug_utils


def test_scheduler_service():
    """测试调度器服务"""

    print("=== SchedulerService 测试开始 ===\n")

    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    # 1. 创建应用控制器
    print("1. 创建应用控制器...")
    app_controller = AppController(project_root_path=str(current_dir))

    # 2. 注册服务
    print("2. 注册服务...")
    registration_results = app_controller.auto_register_services()

    for service_name, success in registration_results.items():
        status = "✅" if success else "❌"
        print(f"   {service_name}: {status}")

    # 3. 获取调度器服务
    print("\n3. 获取调度器服务...")
    scheduler_service = app_controller.get_service('scheduler')
    if not scheduler_service:
        print("❌ 调度器服务获取失败")
        return
    print("✅ 调度器服务获取成功")

    # 4. 测试服务状态
    print("\n4. 测试服务状态...")
    status = scheduler_service.get_status()
    print(f"   服务状态: {json.dumps(status, indent=2, ensure_ascii=False, default=str)}")

    # 5. 测试添加定时任务
    print("\n5. 测试添加定时任务...")

    # 添加测试任务
    def test_task():
        print("🚀 测试任务执行了！")

    success = scheduler_service.add_daily_task(
        task_name="test_task",
        time_str="23:59",
        task_func=test_task
    )
    print(f"   添加测试任务: {'✅' if success else '❌'}")

    # 6. 测试列出任务
    print("\n6. 测试列出任务...")
    tasks = scheduler_service.list_tasks()
    for task in tasks:
        print(f"   📅 {task['name']} | ⏰ {task.get('time', '未配置')} | ⏭️ {task['next_run']}")

    # 7. 测试卡片消息生成
    print("\n7. 测试卡片消息生成...")

    # 创建MessageProcessor来测试卡片生成
    message_processor = MessageProcessor(app_controller=app_controller)

    # 测试日程卡片
    print("   测试日程卡片...")
    schedule_result = message_processor.create_scheduled_message("daily_schedule")
    schedule_success = schedule_result.success and schedule_result.response_content
    print(f"   日程卡片生成: {'✅' if schedule_success else '❌'}")
    if not schedule_success:
        print(f"   错误: {schedule_result.error_message}")

    # 测试B站更新卡片
    print("   测试B站更新卡片...")
    bili_result = message_processor.create_scheduled_message("bilibili_updates", sources=["favorites"])
    bili_success = bili_result.success and bili_result.response_content
    print(f"   B站更新卡片生成: {'✅' if bili_success else '❌'}")
    if not bili_success:
        print(f"   错误: {bili_result.error_message}")

    # 8. 显示卡片内容
    print("\n8. 显示卡片内容...")

    if schedule_success:
        print("\n--- 日程提醒卡片 ---")
        print(json.dumps(schedule_result.response_content, indent=2, ensure_ascii=False))

    if bili_success:
        print("\n--- B站更新卡片 ---")
        print(json.dumps(bili_result.response_content, indent=2, ensure_ascii=False))

    # 9. 清理测试任务
    print("\n9. 清理测试任务...")
    success = scheduler_service.remove_task("test_task")
    print(f"   移除测试任务: {'✅' if success else '❌'}")

    print("\n=== SchedulerService 测试完成 ===")


def test_message_processor_scheduled_integration():
    """测试MessageProcessor与定时任务的集成"""

    print("\n=== MessageProcessor 定时任务集成测试 ===\n")

    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    # 1. 创建应用控制器
    app_controller = AppController(project_root_path=str(current_dir))
    registration_results = app_controller.auto_register_services()

    # 2. 创建消息处理器
    message_processor = MessageProcessor(app_controller=app_controller)

    # 3. 测试定时消息创建
    print("1. 测试定时消息创建...")

    # 测试日程消息
    schedule_result = message_processor.create_scheduled_message("daily_schedule")
    print(f"   日程消息创建: {'✅' if schedule_result.success else '❌'}")
    if not schedule_result.success:
        print(f"   错误: {schedule_result.error_message}")

    # 测试B站更新消息
    bili_result = message_processor.create_scheduled_message("bilibili_updates", sources=["favorites"])
    print(f"   B站更新消息创建: {'✅' if bili_result.success else '❌'}")
    if not bili_result.success:
        print(f"   错误: {bili_result.error_message}")

    # 4. 显示消息内容
    if schedule_result.success:
        print("\n--- 定时日程消息 ---")
        print(json.dumps(schedule_result.response_content, indent=2, ensure_ascii=False))

    if bili_result.success:
        print("\n--- 定时B站更新消息 ---")
        print(json.dumps(bili_result.response_content, indent=2, ensure_ascii=False))

    print("\n=== MessageProcessor 定时任务集成测试完成 ===")


def test_system_health_check():
    """测试系统健康检查"""

    print("\n=== 系统健康检查测试 ===\n")

    # 加载环境变量
    load_dotenv(os.path.join(current_dir, ".env"))

    # 创建应用控制器
    app_controller = AppController(project_root_path=str(current_dir))
    registration_results = app_controller.auto_register_services()

    # 执行健康检查
    health_status = app_controller.health_check()

    print(f"系统状态: {health_status['overall_status']}")
    print(f"服务统计: {health_status['summary']}")

    print("\n服务详情:")
    for service_name, service_info in health_status['services'].items():
        status = service_info['status']
        status_icon = {
            'healthy': '✅',
            'unhealthy': '⚠️',
            'uninitialized': '⏳',
            'error': '❌'
        }.get(status, '❓')

        print(f"  {status_icon} {service_name}: {status}")

        # 显示调度器服务的详细信息（如果有的话）
        if service_name == 'scheduler' and service_info.get('details'):
            details = service_info['details']
            # 检查是否有具体的状态信息
            if details.get('details'):
                scheduler_details = details['details']
                print(f"    - 调度器活跃: {scheduler_details.get('scheduler_active', 'N/A')}")
                print(f"    - 任务数量: {scheduler_details.get('total_tasks', 0)}")
                print(f"    - 已注册函数: {scheduler_details.get('scheduled_functions', [])}")
            else:
                print(f"    - 初始化状态: {details.get('initialized', 'N/A')}")
                print(f"    - 可用状态: {details.get('available', 'N/A')}")

    print("\n=== 系统健康检查测试完成 ===")


if __name__ == "__main__":
    # 运行所有测试
    test_scheduler_service()
    test_message_processor_scheduled_integration()
    test_system_health_check()

    print("\n🎉 所有测试已完成！")