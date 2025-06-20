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
    # UI绑定相关字段 - 支持多种前端
    ui_message_id: Optional[str] = None  # 关联的UI消息ID（卡片、页面等）
    ui_type: str = "card"       # UI类型 ("card", "page", "dialog"等)
    update_count: int = 0       # 更新次数
    last_update_time: float = 0 # 最后更新时间
    # 重试相关字段
    update_retry_count: int = 0 # 更新重试次数
    max_update_retries: int = 3 # 最大重试次数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingOperation':
        """从字典创建"""
        data['status'] = OperationStatus(data['status'])

        # 为旧数据设置默认的ui_type
        if 'ui_type' not in data:
            data['ui_type'] = 'card'

        # 为旧数据设置默认的重试相关字段
        if 'update_retry_count' not in data:
            data['update_retry_count'] = 0
        if 'max_update_retries' not in data:
            data['max_update_retries'] = 3

        return cls(**data)

    def is_expired(self) -> bool:
        """检查是否已过期"""
        return self.get_remaining_time() <= 0

    def get_remaining_time(self) -> int:
        """获取剩余时间（秒）- 使用固定间隔计算避免时间跳跃"""
        remaining = self.expire_time - time.time()
        return max(0, int(remaining))

    def get_remaining_time_text(self) -> str:
        """获取剩余时间文本 - 按用户规则优化显示"""
        remaining = self.get_remaining_time()
        if remaining <= 0:
            return "已过期"

        # 按用户要求的显示规则
        if remaining <= 5:
            return "(即将执行)"
        else:
            # 超过5秒时，显示最接近的5秒倍数
            display_seconds = ((remaining + 4) // 5) * 5  # 向上取整到5的倍数
            minutes = display_seconds // 60
            seconds = display_seconds % 60
            if minutes > 0:
                return f"({minutes}时{seconds}分)"
            else:
                return f"({seconds}s)"

    def needs_ui_update(self, interval_seconds: int = 1) -> bool:
        """检查是否需要更新UI"""
        if self.status != OperationStatus.PENDING:
            return False
        if not self.ui_message_id:
            return False

        # 简化更新逻辑 - 统一5秒间隔，确保用户体验
        actual_interval = 5

        # 使用创建时间作为基准，计算应该更新的时间点
        elapsed_since_creation = time.time() - self.created_time
        expected_updates = int(elapsed_since_creation / actual_interval)

        # 检查是否到了下一个更新时间点
        return self.update_count < expected_updates

    def can_retry_update(self) -> bool:
        """检查是否可以重试更新"""
        return self.update_retry_count < self.max_update_retries


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

        # UI更新推送相关 - 支持多种前端
        self.ui_update_callbacks: Dict[str, Callable] = {}  # ui_type -> callback
        self.auto_update_enabled: bool = True
        self.update_interval: int = 1
        self.max_updates: int = 60
        self._update_thread: Optional[threading.Thread] = None
        self._stop_update_flag: bool = False

        # 加载已保存的操作
        self._load_operations()

        # 启动清理定时器
        self._start_cleanup_timer()

        # 启动自动更新线程
        self._start_auto_update_thread()

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

        debug_utils.log_and_print(f"✅ 添加新操作到缓存，id: {operation_id}", log_level="INFO")
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

    def confirm_operation(self, operation_id: str, force_execute: bool = False) -> bool:
        """
        确认操作

        Args:
            operation_id: 操作ID
            force_execute: 是否强制执行（用于自动确认，跳过过期检查）

        Returns:
            bool: 是否成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation:
            return False

        if operation.status != OperationStatus.PENDING:
            return False

        # 只有在非强制执行时才检查过期
        if operation.is_expired() and not force_execute:
            operation.status = OperationStatus.EXPIRED
            self._save_operations()
            return False

        # 取消定时器
        self._cancel_timer(operation_id)

        # 执行操作
        success = self._execute_operation(operation)

        if success:
            operation.status = OperationStatus.EXECUTED

            # 更新UI显示最终状态
            self._update_ui_for_completed_operation(operation, "已完成", "success")
        else:
            operation.status = OperationStatus.CONFIRMED  # 标记为确认但执行失败
            debug_utils.log_and_print(f"❌ 操作确认但执行失败: [{operation_id[:20]}...]", log_level="ERROR")

            # 更新UI显示失败状态
            self._update_ui_for_completed_operation(operation, "❌ 执行失败", "error")

        # 在UI更新完成后保存操作状态
        self._save_operations()
        return success

    def cancel_operation(self, operation_id: str, force_execute: bool = False) -> bool:
        """
        取消操作

        Args:
            operation_id: 操作ID
            force_execute: 是否强制执行（用于自动取消，跳过过期检查）

        Returns:
            bool: 是否成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation:
            return False

        if operation.status != OperationStatus.PENDING:
            return False

        # 只有在非强制执行时才检查过期
        if operation.is_expired() and not force_execute:
            operation.status = OperationStatus.EXPIRED
            self._save_operations()
            return False

        # 取消定时器
        self._cancel_timer(operation_id)

        # 更新状态
        operation.status = OperationStatus.CANCELLED

        # 更新UI显示取消状态
        self._update_ui_for_completed_operation(operation, "操作取消", "info")

        # 在UI更新完成后保存操作状态
        self._save_operations()
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

        return True

    def _enforce_user_limit(self, user_id: str) -> None:
        """强制执行用户操作数量限制"""
        user_ops = self.get_user_operations(user_id, OperationStatus.PENDING)

        while len(user_ops) >= self.max_operations_per_user:
            # 按默认操作执行最旧的操作
            oldest_op = min(user_ops, key=lambda op: op.created_time)

            if oldest_op.default_action == "confirm":
                self.confirm_operation(oldest_op.operation_id, force_execute=True)
            else:
                self.cancel_operation(oldest_op.operation_id, force_execute=True)

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
                    self.confirm_operation(operation.operation_id, force_execute=True)
                else:
                    self.cancel_operation(operation.operation_id, force_execute=True)

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
            return f"({seconds}s)"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"({minutes}分{secs}秒)" if secs > 0 else f"({minutes}分)"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"({hours}时{minutes}分)" if minutes > 0 else f"({hours}时)"

    def _start_cleanup_timer(self) -> None:
        """启动清理定时器"""
        def cleanup():
            try:
                expired_ops = []
                completed_ops = []
                current_time = time.time()

                for op_id, operation in list(self.pending_operations.items()):
                    # 清理1：过期但未处理的操作
                    if operation.status == OperationStatus.PENDING and operation.is_expired():
                        expired_ops.append(op_id)
                        debug_utils.log_and_print(f"⏰ 操作 {op_id} 已过期", log_level="INFO")

                    # 清理2：已完成操作（超过1小时）
                    elif operation.status in [OperationStatus.EXECUTED, OperationStatus.CANCELLED, OperationStatus.EXPIRED]:
                        if current_time - operation.created_time > 3600:  # 1小时
                            completed_ops.append(op_id)

                    # 清理3：异常状态的操作（超过24小时）
                    elif current_time - operation.created_time > 86400:  # 24小时
                        expired_ops.append(op_id)
                        debug_utils.log_and_print(f"🧹 清理异常状态操作 {op_id} (状态: {operation.status.value})", log_level="WARNING")

                # 执行清理
                total_cleaned = 0

                # 清理过期操作
                for op_id in expired_ops:
                    operation = self.pending_operations.pop(op_id, None)
                    if operation:
                        self._remove_from_user_index(operation.user_id, op_id)
                        self._cancel_timer(op_id)
                        total_cleaned += 1

                # 清理已完成操作
                for op_id in completed_ops:
                    operation = self.pending_operations.pop(op_id, None)
                    if operation:
                        self._remove_from_user_index(operation.user_id, op_id)
                        self._cancel_timer(op_id)
                        total_cleaned += 1

                if total_cleaned > 0:
                    self._save_operations()
                    debug_utils.log_and_print(f"🧹 清理了 {total_cleaned} 个过期/完成操作", log_level="INFO")

                # 内存状态检查
                pending_count = len([op for op in self.pending_operations.values() if op.status == OperationStatus.PENDING])
                if pending_count > 100:  # 警告阈值
                    debug_utils.log_and_print(f"⚠️ pending操作数量较多: {pending_count}", log_level="WARNING")

            except Exception as e:
                debug_utils.log_and_print(f"❌ 定期清理异常: {e}", log_level="ERROR")

            # 设置下次清理 - 根据操作数量调整清理频率
            operation_count = len(self.pending_operations)
            if operation_count > 50:
                next_cleanup = 300  # 5分钟
            elif operation_count > 10:
                next_cleanup = 900  # 15分钟
            else:
                next_cleanup = 1800  # 30分钟

            timer = threading.Timer(next_cleanup, cleanup)
            timer.daemon = True
            timer.start()

        # 初始清理 - 1分钟后开始
        timer = threading.Timer(60, cleanup)
        timer.daemon = True
        timer.start()

    def _remove_from_user_index(self, user_id: str, operation_id: str) -> None:
        """从用户操作索引中移除操作"""
        if user_id in self.user_operations:
            try:
                self.user_operations[user_id].remove(operation_id)
                # 如果用户没有操作了，清理用户索引
                if not self.user_operations[user_id]:
                    del self.user_operations[user_id]
            except ValueError:
                pass  # 操作ID不在列表中，忽略

    def force_cleanup(self) -> Dict[str, int]:
        """
        强制清理所有过期和已完成的操作

        Returns:
            Dict[str, int]: 清理统计信息
        """
        cleanup_stats = {
            "expired": 0,
            "completed": 0,
            "total": 0
        }

        current_time = time.time()
        to_remove = []

        for op_id, operation in self.pending_operations.items():
            if operation.status == OperationStatus.PENDING and operation.is_expired():
                to_remove.append((op_id, "expired"))
            elif operation.status in [OperationStatus.EXECUTED, OperationStatus.CANCELLED, OperationStatus.EXPIRED]:
                to_remove.append((op_id, "completed"))

        for op_id, reason in to_remove:
            operation = self.pending_operations.pop(op_id, None)
            if operation:
                self._remove_from_user_index(operation.user_id, op_id)
                self._cancel_timer(op_id)
                cleanup_stats[reason] += 1
                cleanup_stats["total"] += 1

        if cleanup_stats["total"] > 0:
            self._save_operations()
            debug_utils.log_and_print(f"🧹 强制清理完成: {cleanup_stats}", log_level="INFO")

        return cleanup_stats

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        current_time = time.time()
        stats = {
            "total_operations": len(self.pending_operations),
            "status_breakdown": {},
            "user_breakdown": {},
            "age_breakdown": {
                "under_1m": 0,
                "1m_to_5m": 0,
                "5m_to_1h": 0,
                "over_1h": 0
            },
            "active_timers": len(self.timers),
            "oldest_operation": None,
            "newest_operation": None
        }

        oldest_time = float('inf')
        newest_time = 0

        for operation in self.pending_operations.values():
            # 状态统计
            status = operation.status.value
            stats["status_breakdown"][status] = stats["status_breakdown"].get(status, 0) + 1

            # 用户统计
            user_id = operation.user_id
            stats["user_breakdown"][user_id] = stats["user_breakdown"].get(user_id, 0) + 1

            # 年龄统计
            age = current_time - operation.created_time
            if age < 60:
                stats["age_breakdown"]["under_1m"] += 1
            elif age < 300:
                stats["age_breakdown"]["1m_to_5m"] += 1
            elif age < 3600:
                stats["age_breakdown"]["5m_to_1h"] += 1
            else:
                stats["age_breakdown"]["over_1h"] += 1

            # 最新最旧操作
            if operation.created_time < oldest_time:
                oldest_time = operation.created_time
                stats["oldest_operation"] = {
                    "id": operation.operation_id,
                    "age_seconds": int(age),
                    "status": status
                }

            if operation.created_time > newest_time:
                newest_time = operation.created_time
                stats["newest_operation"] = {
                    "id": operation.operation_id,
                    "age_seconds": int(current_time - operation.created_time),
                    "status": status
                }

        return stats

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

    def _start_auto_update_thread(self) -> None:
        """启动自动更新线程"""
        if not self.auto_update_enabled:
            return

        def auto_update():
            debug_utils.log_and_print("🔄 启动UI自动更新线程", log_level="INFO")
            while not self._stop_update_flag:
                try:
                    updated_count = 0
                    retry_count = 0

                    # 第一步：独立的过期检测 - 优先处理所有过期操作
                    expired_operations = []
                    for op_id, operation in list(self.pending_operations.items()):
                        if operation.status == OperationStatus.PENDING and operation.is_expired():
                            expired_operations.append((op_id, operation))

                    # 处理所有过期操作
                    for op_id, operation in expired_operations:
                        debug_utils.log_and_print(f"⏰ 倒计时结束，执行默认操作: {operation.default_action} [{op_id[:20]}...]", log_level="INFO")
                        if operation.default_action == "confirm":
                            self.confirm_operation(op_id, force_execute=True)
                        else:
                            self.cancel_operation(op_id, force_execute=True)

                    # 第二步：收集需要UI更新的操作（排除已过期的）
                    operations_to_update = []
                    max_batch_size = 10

                    for op_id, operation in list(self.pending_operations.items()):
                        if operation.needs_ui_update(self.update_interval):
                            if len(operations_to_update) < max_batch_size:
                                operations_to_update.append((op_id, operation))
                            else:
                                break

                    # 移除之前的专项检测（已经在第一步处理了）

                    # 第三步：处理UI更新
                    for op_id, operation in operations_to_update:
                        ui_callback = self.ui_update_callbacks.get(operation.ui_type)

                        if ui_callback and operation.update_count < self.max_updates:
                            # 更新操作数据中的倒计时文本
                            old_time_text = operation.operation_data.get('hold_time', '')
                            operation.operation_data['hold_time'] = operation.get_remaining_time_text()
                            new_time_text = operation.operation_data['hold_time']

                            # 调用UI更新回调
                            success = ui_callback(operation)

                            if success:
                                operation.last_update_time = time.time()
                                operation.update_count += 1
                                operation.update_retry_count = 0  # 重置重试计数
                                updated_count += 1
                            else:
                                # 更新失败，进行重试逻辑
                                operation.update_retry_count += 1
                                retry_count += 1

                except Exception as e:
                    debug_utils.log_and_print(f"❌ UI自动更新异常: {e}", log_level="ERROR")

                time.sleep(self.update_interval)

            debug_utils.log_and_print("⏹️ UI自动更新线程已停止", log_level="INFO")

        self._update_thread = threading.Thread(target=auto_update, daemon=True)
        self._update_thread.start()

    def configure_auto_update(self, enabled: bool = True, interval: int = 1, max_updates: int = 60) -> None:
        """
        配置自动更新参数

        Args:
            enabled: 是否启用自动更新
            interval: 更新间隔（秒）
            max_updates: 最大更新次数
        """
        self.auto_update_enabled = enabled
        self.update_interval = interval
        self.max_updates = max_updates

    def stop_auto_update(self) -> None:
        """停止自动更新线程"""
        if self._update_thread and self._update_thread.is_alive():
            debug_utils.log_and_print("⏹️ 正在停止UI自动更新线程...", log_level="INFO")
            self._stop_update_flag = True
            self._update_thread.join(timeout=5)  # 5秒超时

            if self._update_thread.is_alive():
                debug_utils.log_and_print("⚠️ 自动更新线程未能正常停止", log_level="WARNING")
            else:
                debug_utils.log_and_print("✅ 自动更新线程已停止", log_level="INFO")

    def register_ui_update_callback(self, ui_type: str, callback: Callable[[PendingOperation], bool]) -> None:
        """
        注册UI更新回调函数（支持多种前端）

        Args:
            ui_type: UI类型 ("card", "page", "dialog"等)
            callback: 回调函数，接收PendingOperation，返回bool表示是否更新成功
        """
        self.ui_update_callbacks[ui_type] = callback
        debug_utils.log_and_print(f"✅ 注册UI更新回调: {ui_type}", log_level="INFO")

    def bind_ui_message(self, operation_id: str, message_id: str, ui_type: str = "card") -> bool:
        """
        绑定操作和UI消息ID

        Args:
            operation_id: 操作ID
            message_id: UI消息ID
            ui_type: UI类型

        Returns:
            bool: 是否绑定成功
        """
        operation = self.pending_operations.get(operation_id)
        if not operation:
            debug_utils.log_and_print(f"❌ 绑定UI消息失败: 操作不存在 {operation_id}", log_level="ERROR")
            return False

        operation.ui_message_id = message_id
        operation.ui_type = ui_type
        operation.last_update_time = time.time()
        self._save_operations()

        debug_utils.log_and_print(f"🔗 UI消息绑定成功, ui_type={ui_type}", log_level="INFO")
        return True

    def _update_ui_for_completed_operation(self, operation, result_text: str, result_type: str):
        """为已完成的操作更新UI显示最终状态"""
        try:
            if not operation.ui_message_id:
                debug_utils.log_and_print(f"❌ 最终状态UI更新跳过: 缺少ui_message_id [{operation.operation_id[:20]}...]", log_level="WARNING")
                return

            if operation.ui_type not in self.ui_update_callbacks:
                debug_utils.log_and_print(f"❌ 最终状态UI更新跳过: 未找到{operation.ui_type}回调 [{operation.operation_id[:20]}...]", log_level="WARNING")
                return

            # 更新操作数据以显示最终状态
            operation.operation_data.update({
                'finished': True,
                'hold_time': '',
                'result': f" | {result_text}",
                'result_type': result_type
            })

            # 调用UI更新
            ui_callback = self.ui_update_callbacks[operation.ui_type]
            success = ui_callback(operation)

            if not success:
                debug_utils.log_and_print(f"❌ 最终状态UI更新失败: [{operation.operation_id[:20]}...]", log_level="ERROR")

        except Exception as e:
            debug_utils.log_and_print(f"❌ 最终状态UI更新异常: {e} [{operation.operation_id[:20]}...]", log_level="ERROR")