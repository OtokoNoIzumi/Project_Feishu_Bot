"""
统一指令系统

定义了应用层统一的指令格式和结果格式
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class Command:
    """统一的指令对象"""
    action: str                    # 指令动作，如 "notion.get_data", "media.process_audio"
    params: Dict[str, Any]        # 指令参数
    context: Dict[str, Any]       # 上下文信息（用户ID、会话ID等）

    def __post_init__(self):
        """确保params和context是字典"""
        if self.params is None:
            self.params = {}
        if self.context is None:
            self.context = {}


@dataclass
class CommandResult:
    """统一的指令结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """确保extra是字典"""
        if self.extra is None:
            self.extra = {}

    @classmethod
    def success_result(cls, data: Any = None, **extra) -> 'CommandResult':
        """创建成功结果"""
        return cls(success=True, data=data, extra=extra)

    @classmethod
    def error_result(cls, error: str, **extra) -> 'CommandResult':
        """创建错误结果"""
        return cls(success=False, error=error, extra=extra)