"""
前端适配器基类

定义所有前端适配器的通用接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from Module.Application.command import Command, CommandResult
from Module.Common.scripts.common import debug_utils


class Adapter(ABC):
    """前端适配器基类"""

    def __init__(self, app_controller: Any):
        """
        初始化适配器

        Args:
            app_controller: 应用控制器实例
        """
        self.app = app_controller
        self.is_running = False

    @abstractmethod
    def start(self) -> None:
        """启动前端服务"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止前端服务"""
        pass

    @abstractmethod
    def handle_user_input(self, user_input: Any) -> Optional[Command]:
        """
        将前端用户输入转换为统一指令

        Args:
            user_input: 前端特定的用户输入格式

        Returns:
            Optional[Command]: 转换后的统一指令，如果无需处理返回None
        """
        pass

    @abstractmethod
    def handle_command_result(self, result: CommandResult, context: Dict[str, Any]) -> None:
        """
        将指令结果转换为前端输出

        Args:
            result: 指令执行结果
            context: 执行上下文信息
        """
        pass

    def execute_user_command(self, user_input: Any, context: Dict[str, Any] = None) -> None:
        """
        执行用户指令的完整流程

        Args:
            user_input: 用户输入
            context: 额外的上下文信息
        """
        if context is None:
            context = {}

        try:
            # 转换为统一指令
            command = self.handle_user_input(user_input)
            if command is None:
                return

            # 合并上下文
            command.context.update(context)

            # 执行指令
            result = self.app.execute_command(command)

            # 处理结果
            self.handle_command_result(result, command.context)

        except Exception as e:
            debug_utils.log_and_print(f"执行用户指令失败: {e}", log_level="ERROR")
            # 创建错误结果
            error_result = CommandResult.error_result(f"处理请求时发生错误: {str(e)}")
            self.handle_command_result(error_result, context)

    def log_and_print(self, *messages, log_level="INFO"):
        """
        日志和打印函数

        Args:
            *messages: 消息内容
            log_level: 日志级别
        """
        debug_utils.log_and_print(*messages, log_level=log_level)