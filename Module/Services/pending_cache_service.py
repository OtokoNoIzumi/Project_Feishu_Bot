"""
缓存业务服务

专门处理需要缓存和确认的业务操作，支持倒计时和自动执行
"""

import time
import json
import asyncio
import threading
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, asdict
from enum import Enum

from Module.Common.scripts.common import debug_utils
from .service_decorators import service_operation_safe, cache_operation_safe


class OperationStatus(Enum):
    """操作状态枚举"""
    PENDING = "pending"      # 等待确认
    CONFIRMED = "confirmed"  # 已确认
    CANCELLED = "cancelled"  # 已取消
    EXPIRED = "expired"      # 已过期
    EXECUTED = "executed"    # 已执行


@dataclass
class PendingOperation:
    """待处理操作"""
    operation_id: str           # 操作ID
    user_id: str               # 用户ID
    operation_type: str        # 操作类型
    operation_data: Dict[str, Any]  # 操作数据
    admin_input: str           # 管理员原始输入
    created_time: float        # 创建时间
    expire_time: float         # 过期时间
    hold_time_text: str        # 倒计时显示文本
    status: OperationStatus    # 操作状态
    default_action: str = "confirm"  # 默认操作 (confirm/cancel)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingOperation':
        """从字典创建"""
        data['status'] = OperationStatus(data['status'])
        return cls(**data)

    def is_expired(self) -> bool:
        """检查是否已过期"""
        return time.time() > self.expire_time

    def get_remaining_time(self) -> int:
        """获取剩余时间（秒）"""
        remaining = self.expire_time - time.time()
        return max(0, int(remaining))

    def get_remaining_time_text(self) -> str:
        """获取剩余时间文本"""
        remaining = self.get_remaining_time()
        if remaining <= 0:
            return "已过期"

        minutes = remaining // 60
        seconds = remaining % 60
        if minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"


class PendingCacheService:
    """缓存业务服务"""

    def __init__(self, cache_dir: str = "cache", max_operations_per_user: int = 2):
        """
        初始化缓存业务服务

        Args:
            cache_dir: 缓存目录
            max_operations_per_user: 每用户最大缓存操作数
        """
        self.cache_dir = cache_dir
        self.max_operations_per_user = max_operations_per_user
        self.pending_operations: Dict[str, PendingOperation] = {}
        self.user_operations: Dict[str, List[str]] = {}  # user_id -> operation_ids

        # 定时器管理
        self.timers: Dict[str, threading.Timer] = {}
        self.executor_callbacks: Dict[str, Callable] = {}  # operation_type -> callback

        # 加载已保存的操作
        self._load_operations()

        # 启动清理定时器
        self._start_cleanup_timer()

    @cache_operation_safe("加载缓存操作失败", return_value={})
    def _load_operations(self) -> None:
        """加载已保存的操作"""
        cache_file = f"{self.cache_dir}/pending_operations.json"
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for op_id, op_data in data.items():
                operation = PendingOperation.from_dict(op_data)

                # 检查是否已过期
                if operation.is_expired():
                    operation.status = OperationStatus.EXPIRED
                    continue

                self.pending_operations[op_id] = operation

                # 重建用户操作索引
                if operation.user_id not in self.user_operations:
                    self.user_operations[operation.user_id] = []
                self.user_operations[operation.user_id].append(op_id)

                # 重新设置定时器
                if operation.status == OperationStatus.PENDING:
                    self._set_expiry_timer(operation)

        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # 文件不存在或格式错误，从空开始
            pass

    @cache_operation_safe("保存缓存操作失败")
    def _save_operations(self) -> None:
        """保存操作到磁盘"""
        cache_file = f"{self.cache_dir}/pending_operations.json"
        import os
        os.makedirs(self.cache_dir, exist_ok=True)

        data = {op_id: op.to_dict() for op_id, op in self.pending_operations.items()}

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_executor(self, operation_type: str, callback: Callable[[PendingOperation], bool]) -> None:
        """
        注册操作执行器

        Args:
            operation_type: 操作类型
            callback: 执行回调函数，返回bool表示是否成功
        """
        self.executor_callbacks[operation_type] = callback
        debug_utils.log_and_print(f"✅ 注册操作执行器: {operation_type}", log_level="INFO")

    def create_operation(self,
                        user_id: str,
                        operation_type: str,
                        operation_data: Dict[str, Any],
                        admin_input: str,
                        hold_time_seconds: int = 30,
                        default_action: str = "confirm") -> str:
        """
        创建新的缓存操作

        Args:
            user_id: 用户ID
            operation_type: 操作类型
            operation_data: 操作数据
            admin_input: 管理员原始输入
            hold_time_seconds: 缓存时间（秒）
            default_action: 默认操作

        Returns:
            str: 操作ID
        """
        # 检查用户操作数量限制
        self._enforce_user_limit(user_id)

        # 生成操作ID
        operation_id = f"{operation_type}_{user_id}_{int(time.time())}"

        # 计算过期时间
        current_time = time.time()
        expire_time = current_time + hold_time_seconds

        # 生成倒计时文本
        hold_time_text = self._format_hold_time(hold_time_seconds)

        # 创建操作
        operation = PendingOperation(
            operation_id=operation_id,
            user_id=user_id,
            operation_type=operation_type,
            operation_data=operation_data,
            admin_input=admin_input,
            created_time=current_time,
            expire_time=expire_time,
            hold_time_text=hold_time_text,
            status=OperationStatus.PENDING,
            default_action=default_action
        )

        # 保存操作
        self.pending_operations[operation_id] = operation

        # 更新用户操作索引
        if user_id not in self.user_operations:
            self.user_operations[user_id] = []
        self.user_operations[user_id].append(operation_id)

        # 设置过期定时器
        self._set_expiry_timer(operation)

        # 保存到磁盘
        self._save_operations()

        debug_utils.log_and_print(f"✅ 创建缓存操作: {operation_id}", log_level="INFO")
        return operation_id

    def get_operation(self, operation_id: str) -> Optional[PendingOperation]:
        """获取操作"""
        return self.pending_operations.get(operation_id)

    def get_user_operations(self, user_id: str, status: Optional[OperationStatus] = None) -> List[PendingOperation]:
        """
        获取用户的操作列表

        Args:
            user_id: 用户ID
            status: 可选的状态过滤

        Returns:
            List[PendingOperation]: 操作列表
        """
        operation_ids = self.user_operations.get(user_id, [])
        operations = [self.pending_operations[op_id] for op_id in operation_ids if op_id in self.pending_operations]

        if status:
            operations = [op for op in operations if op.status == status]

        return operations

    def confirm_operation(self, operation_id: str) -> bool:
        """
        确认操作

        Args:
            operation_id: 操作ID

        Returns:
            bool: 是否成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation:
            return False

        if operation.status != OperationStatus.PENDING:
            return False

        if operation.is_expired():
            operation.status = OperationStatus.EXPIRED
            self._save_operations()
            return False

        # 取消定时器
        self._cancel_timer(operation_id)

        # 执行操作
        success = self._execute_operation(operation)

        if success:
            operation.status = OperationStatus.EXECUTED
        else:
            operation.status = OperationStatus.CONFIRMED  # 标记为确认但执行失败
            debug_utils.log_and_print(f"❌ 操作确认但执行失败: {operation_id}", log_level="ERROR")

        self._save_operations()
        return success

    def cancel_operation(self, operation_id: str) -> bool:
        """
        取消操作

        Args:
            operation_id: 操作ID

        Returns:
            bool: 是否成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation:
            return False

        if operation.status != OperationStatus.PENDING:
            return False

        # 取消定时器
        self._cancel_timer(operation_id)

        # 更新状态
        operation.status = OperationStatus.CANCELLED
        self._save_operations()

        debug_utils.log_and_print(f"✅ 操作已取消: {operation_id}", log_level="INFO")
        return True

    def update_operation_data(self, operation_id: str, new_data: Dict[str, Any]) -> bool:
        """
        更新操作数据

        Args:
            operation_id: 操作ID
            new_data: 新数据

        Returns:
            bool: 是否成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation or operation.status != OperationStatus.PENDING:
            return False

        operation.operation_data.update(new_data)
        self._save_operations()

        debug_utils.log_and_print(f"✅ 操作数据已更新: {operation_id}", log_level="INFO")
        return True

    def _enforce_user_limit(self, user_id: str) -> None:
        """强制执行用户操作数量限制"""
        user_ops = self.get_user_operations(user_id, OperationStatus.PENDING)

        while len(user_ops) >= self.max_operations_per_user:
            # 按默认操作执行最旧的操作
            oldest_op = min(user_ops, key=lambda op: op.created_time)

            if oldest_op.default_action == "confirm":
                self.confirm_operation(oldest_op.operation_id)
            else:
                self.cancel_operation(oldest_op.operation_id)

            # 重新获取用户操作
            user_ops = self.get_user_operations(user_id, OperationStatus.PENDING)

    def _execute_operation(self, operation: PendingOperation) -> bool:
        """执行操作"""
        executor = self.executor_callbacks.get(operation.operation_type)
        if not executor:
            debug_utils.log_and_print(f"❌ 未找到操作执行器: {operation.operation_type}", log_level="ERROR")
            return False

        try:
            return executor(operation)
        except Exception as e:
            debug_utils.log_and_print(f"❌ 操作执行失败: {operation.operation_id}, 错误: {e}", log_level="ERROR")
            return False

    def _set_expiry_timer(self, operation: PendingOperation) -> None:
        """设置过期定时器"""
        remaining_time = operation.get_remaining_time()
        if remaining_time <= 0:
            return

        def on_expire():
            if operation.operation_id in self.pending_operations:
                if operation.default_action == "confirm":
                    self.confirm_operation(operation.operation_id)
                else:
                    self.cancel_operation(operation.operation_id)

        timer = threading.Timer(remaining_time, on_expire)
        timer.start()
        self.timers[operation.operation_id] = timer

    def _cancel_timer(self, operation_id: str) -> None:
        """取消定时器"""
        timer = self.timers.pop(operation_id, None)
        if timer:
            timer.cancel()

    def _format_hold_time(self, seconds: int) -> str:
        """格式化倒计时文本"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}分{secs}秒" if secs > 0 else f"{minutes}分钟"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"

    def _start_cleanup_timer(self) -> None:
        """启动清理定时器"""
        def cleanup():
            expired_ops = []
            for op_id, operation in self.pending_operations.items():
                if operation.status in [OperationStatus.EXECUTED, OperationStatus.CANCELLED, OperationStatus.EXPIRED]:
                    # 清理超过1小时的已完成操作
                    if time.time() - operation.created_time > 3600:
                        expired_ops.append(op_id)

            for op_id in expired_ops:
                operation = self.pending_operations.pop(op_id, None)
                if operation:
                    # 从用户索引中移除
                    user_ops = self.user_operations.get(operation.user_id, [])
                    if op_id in user_ops:
                        user_ops.remove(op_id)
                    self._cancel_timer(op_id)

            if expired_ops:
                self._save_operations()
                debug_utils.log_and_print(f"🧹 清理了 {len(expired_ops)} 个过期操作", log_level="INFO")

            # 设置下次清理
            timer = threading.Timer(1800, cleanup)  # 30分钟后再次清理
            timer.start()

        # 初始清理
        timer = threading.Timer(60, cleanup)  # 1分钟后开始清理
        timer.start()

    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        pending_count = len([op for op in self.pending_operations.values() if op.status == OperationStatus.PENDING])

        return {
            "service_name": "pending_cache",
            "status": "healthy",
            "total_operations": len(self.pending_operations),
            "pending_operations": pending_count,
            "registered_executors": list(self.executor_callbacks.keys()),
            "active_timers": len(self.timers),
            "max_operations_per_user": self.max_operations_per_user
        }