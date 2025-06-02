"""
阶段1 MVP - 基础消息收发

目标：验证新架构的核心优势
1. 业务逻辑与前端分离
2. 调用链路简化
3. 平台无关的设计

重构前 vs 重构后对比：
- 重构前：飞书SDK → 巨大的处理函数 → 各种内嵌逻辑
- 重构后：飞书适配器 → 标准消息处理器 → 清晰的业务逻辑
"""

import os
import sys
import time
import asyncio
from pathlib import Path

# 添加项目根路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from dotenv import load_dotenv

# 导入重构后的模块
from Module.Application.app_controller import AppController
from Module.Business.message_processor import MessageProcessor
from Module.Adapters.feishu_adapter import FeishuAdapter
from Module.Common.scripts.common import debug_utils


class Stage1MVP:
    """
    阶段1 MVP应用

    展示重构后架构的优势：
    1. 清晰的层次分离
    2. 简化的调用链路
    3. 平台无关的业务逻辑
    """

    def __init__(self, project_root_path: str = ""):
        """初始化MVP应用"""
        self.project_root_path = project_root_path or current_dir

        # 加载环境变量
        load_dotenv(os.path.join(self.project_root_path, ".env"))

        # 初始化应用控制器
        self.app_controller = AppController(self.project_root_path)

        # 自动注册和初始化服务
        self._setup_services()

        # 初始化业务处理器
        self.message_processor = MessageProcessor(self.app_controller)

        # 初始化飞书适配器
        self.feishu_adapter = FeishuAdapter(self.message_processor, self.app_controller)

    def _setup_services(self):
        """设置服务"""
        debug_utils.log_and_print("初始化服务层...", log_level="INFO")

        # 注册服务
        register_results = self.app_controller.auto_register_services()
        debug_utils.log_and_print(f"服务注册结果: {register_results}", log_level="INFO")

        # 初始化服务
        init_results = self.app_controller.initialize_all_services()
        debug_utils.log_and_print(f"服务初始化结果: {init_results}", log_level="INFO")

    def show_architecture_comparison(self):
        """展示架构对比"""
        print("\n" + "="*60)
        print("阶段1 MVP - 架构对比")
        print("="*60)

        print("\n【重构前的调用链路】:")
        print("飞书WebSocket → do_p2_im_message_receive_v1() 巨大函数")
        print("  ├── 事件去重逻辑")
        print("  ├── 用户信息获取")
        print("  ├── 消息类型判断")
        print("  ├── 各种if-elif业务处理")
        print("  ├── 内嵌的发送消息函数")
        print("  └── 直接飞书API调用")
        print("问题：所有逻辑混在一起，难以测试和扩展")

        print("\n【重构后的调用链路】:")
        print("飞书适配器 → 消息处理器 → 具体业务逻辑")
        print("  ├── FeishuAdapter: 纯协议转换")
        print("  ├── MessageProcessor: 平台无关业务逻辑")
        print("  ├── AppController: 统一服务调用")
        print("  └── Services: 独立的功能服务")
        print("优势：层次清晰，职责分离，易于测试和扩展")

    def show_status_report(self):
        """展示系统状态报告"""
        print("\n" + "="*60)
        print("系统状态报告")
        print("="*60)

        # 应用控制器状态
        controller_status = self.app_controller.get_service_status()
        print(f"\n【应用控制器】:")
        print(f"  项目根路径: {controller_status['controller']['project_root']}")
        print(f"  服务总数: {controller_status['controller']['total_services']}")
        print(f"  已初始化: {controller_status['controller']['initialized_services']}")

        # 各服务状态
        print(f"\n【服务状态】:")
        for service_name, status in controller_status['services'].items():
            availability = "✓ 可用" if status.get('available', False) else "✗ 不可用"
            print(f"  {service_name}: {availability}")

        # 消息处理器状态
        processor_status = self.message_processor.get_status()
        print(f"\n【消息处理器】:")
        print(f"  类型: {processor_status['processor_type']}")
        print(f"  管理员ID: {processor_status['admin_id'] or '未配置'}")
        print(f"  应用控制器: {'✓ 已连接' if processor_status['app_controller_available'] else '✗ 未连接'}")

        # 飞书适配器状态
        adapter_status = self.feishu_adapter.get_status()
        print(f"\n【飞书适配器】:")
        print(f"  类型: {adapter_status['adapter_type']}")
        print(f"  应用ID: {adapter_status['app_id']}")
        print(f"  日志级别: {adapter_status['log_level']}")
        print(f"  消息处理器: {'✓ 已连接' if adapter_status['message_processor_available'] else '✗ 未连接'}")

    def run_functional_test(self):
        """运行功能测试"""
        print("\n" + "="*60)
        print("功能测试")
        print("="*60)

        from Module.Business.message_processor import MessageContext
        from datetime import datetime

        # 测试场景1：问候消息
        print("\n【测试1：问候消息】")
        context1 = MessageContext(
            user_id="test_user_001",
            user_name="测试用户",
            message_type="text",
            content="你好",
            timestamp=datetime.now(),
            event_id="test_event_001"
        )

        result1 = self.message_processor.process_message(context1)
        print(f"输入: {context1.content}")
        print(f"输出: {result1.response_content['text'] if result1.success else result1.error_message}")
        print(f"状态: {'✓ 成功' if result1.success else '✗ 失败'}")

        # 测试场景2：帮助消息
        print("\n【测试2：帮助消息】")
        context2 = MessageContext(
            user_id="test_user_001",
            user_name="测试用户",
            message_type="text",
            content="帮助",
            timestamp=datetime.now(),
            event_id="test_event_002"
        )

        result2 = self.message_processor.process_message(context2)
        print(f"输入: {context2.content}")
        print(f"输出类型: {result2.response_type}")
        print(f"状态: {'✓ 成功' if result2.success else '✗ 失败'}")

        # 测试场景3：重复事件处理
        print("\n【测试3：重复事件处理】")
        result3 = self.message_processor.process_message(context1)  # 重复的event_id
        print(f"重复事件处理: {'✓ 正确跳过' if not result3.should_reply else '✗ 未正确处理'}")

        # 测试场景4：默认回复
        print("\n【测试4：默认回复】")
        context4 = MessageContext(
            user_id="test_user_001",
            user_name="测试用户",
            message_type="text",
            content="随意的测试消息",
            timestamp=datetime.now(),
            event_id="test_event_004"
        )

        result4 = self.message_processor.process_message(context4)
        print(f"输入: {context4.content}")
        print(f"输出: {result4.response_content['text'] if result4.success else result4.error_message}")
        print(f"状态: {'✓ 成功' if result4.success else '✗ 失败'}")

    def start(self, mode="sync"):
        """启动MVP应用"""
        print("\n" + "="*60)
        print("启动阶段1 MVP - 基础消息收发")
        print("="*60)

        # 展示对比和状态
        self.show_architecture_comparison()
        self.show_status_report()
        self.run_functional_test()

        print("\n" + "="*60)
        print("启动飞书WebSocket连接...")
        print("="*60)

        try:
            if mode == "async":
                # 异步模式
                asyncio.run(self._run_async())
            else:
                # 同步模式
                self._run_sync()
        except KeyboardInterrupt:
            print("\n程序被用户中断")
        except Exception as e:
            debug_utils.log_and_print(f"程序运行出错: {e}", log_level="ERROR")
        finally:
            self.feishu_adapter.stop()
            print("飞书适配器已停止")

    def _run_sync(self):
        """同步运行模式"""
        debug_utils.log_and_print("使用同步模式启动飞书适配器", log_level="INFO")
        self.feishu_adapter.start()

    async def _run_async(self):
        """异步运行模式"""
        debug_utils.log_and_print("使用异步模式启动飞书适配器", log_level="INFO")
        await self.feishu_adapter.start_async()

        # 保持运行
        while True:
            await asyncio.sleep(10)


def main():
    """主函数"""
    print("阶段1 MVP - 基础消息收发")
    print("验证重构后架构的优势")

    # 创建MVP应用
    mvp_app = Stage1MVP()

    # 启动应用
    mvp_app.start(mode="sync")


if __name__ == "__main__":
    main()