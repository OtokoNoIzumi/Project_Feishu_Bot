"""
信息汇总服务

专门处理来自各种定时任务的信息收集和AI汇总，避免信息冲刷
"""

import time
import json
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from Module.Common.scripts.common import debug_utils
from .service_decorators import service_operation_safe
from Module.Services.constants import ServiceNames


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1      # 一般信息
    NORMAL = 2   # 普通消息
    HIGH = 3     # 重要消息
    URGENT = 4   # 紧急消息


@dataclass
class PendingMessage:
    """待汇总消息"""
    message_id: str
    source_type: str        # 来源类型（如 "daily_schedule", "bili_updates"）
    content: Dict[str, Any] # 消息内容
    priority: MessagePriority
    created_time: float
    user_id: str
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingMessage':
        data['priority'] = MessagePriority(data['priority'])
        return cls(**data)


class MessageAggregationService:
    """信息汇总服务"""

    def __init__(self, app_controller=None):
        """
        初始化信息汇总服务

        Args:
            app_controller: 应用控制器实例
        """
        self.app_controller = app_controller
        self.pending_messages: Dict[str, PendingMessage] = {}
        self.aggregation_rules: Dict[str, Dict] = {}

        # 聚合配置
        self.aggregation_window = 300  # 聚合时间窗口（秒），默认5分钟
        self.max_messages_per_aggregation = 10  # 每次聚合最大消息数
        self.min_messages_for_aggregation = 2   # 触发聚合的最小消息数

        # 定时器
        self.aggregation_timer: Optional[threading.Timer] = None
        self.cleanup_timer: Optional[threading.Timer] = None

        # 回调函数
        self.aggregation_callback: Optional[Callable] = None

        self._start_aggregation_timer()
        self._start_cleanup_timer()

    def register_aggregation_callback(self, callback: Callable[[List[PendingMessage], str], bool]) -> None:
        """
        注册聚合回调函数

        Args:
            callback: 回调函数，接收消息列表和聚合摘要，返回是否发送成功
        """
        self.aggregation_callback = callback

    def add_message(self,
                   source_type: str,
                   content: Dict[str, Any],
                   user_id: str,
                   priority: MessagePriority = MessagePriority.NORMAL,
                   metadata: Dict[str, Any] = None) -> str:
        """
        添加待汇总消息

        Args:
            source_type: 消息来源类型
            content: 消息内容
            user_id: 用户ID
            priority: 消息优先级
            metadata: 元数据

        Returns:
            str: 消息ID
        """
        message_id = f"{source_type}_{user_id}_{int(time.time() * 1000)}"

        message = PendingMessage(
            message_id=message_id,
            source_type=source_type,
            content=content,
            priority=priority,
            created_time=time.time(),
            user_id=user_id,
            metadata=metadata or {}
        )

        self.pending_messages[message_id] = message

        debug_utils.log_and_print(f"📝 添加待汇总消息: {source_type} [{content}]", log_level="INFO")

        # 检查是否需要立即触发聚合
        self._check_immediate_aggregation(user_id)

        return message_id

    def configure_aggregation(self,
                            window_seconds: int = 300,
                            max_messages: int = 10,
                            min_messages: int = 2) -> None:
        """
        配置聚合参数

        Args:
            window_seconds: 聚合时间窗口
            max_messages: 每次聚合最大消息数
            min_messages: 触发聚合的最小消息数
        """
        self.aggregation_window = window_seconds
        self.max_messages_per_aggregation = max_messages
        self.min_messages_for_aggregation = min_messages

    def set_aggregation_rule(self, source_type: str, rule: Dict[str, Any]) -> None:
        """
        设置特定来源的聚合规则

        Args:
            source_type: 来源类型
            rule: 聚合规则配置
        """
        self.aggregation_rules[source_type] = rule

    @service_operation_safe("消息聚合失败")
    def _check_immediate_aggregation(self, user_id: str) -> None:
        """检查是否需要立即触发聚合"""
        user_messages = [msg for msg in self.pending_messages.values() if msg.user_id == user_id]

        # 检查紧急消息
        urgent_messages = [msg for msg in user_messages if msg.priority == MessagePriority.URGENT]
        if urgent_messages:
            self._trigger_aggregation(user_id, reason="urgent_message")
            return

        # 检查消息数量阈值
        if len(user_messages) >= self.max_messages_per_aggregation:
            self._trigger_aggregation(user_id, reason="max_messages_reached")

    @service_operation_safe("定时聚合失败")
    def _trigger_aggregation(self, user_id: str = None, reason: str = "scheduled") -> None:
        """触发消息聚合"""
        if user_id:
            user_messages = [msg for msg in self.pending_messages.values() if msg.user_id == user_id]
        else:
            # 全局聚合，按用户分组
            user_groups = {}
            for msg in self.pending_messages.values():
                if msg.user_id not in user_groups:
                    user_groups[msg.user_id] = []
                user_groups[msg.user_id].append(msg)

            # 处理每个用户的消息
            for uid, messages in user_groups.items():
                if len(messages) >= self.min_messages_for_aggregation:
                    self._process_user_aggregation(uid, messages, reason)
            return

        if len(user_messages) >= self.min_messages_for_aggregation:
            self._process_user_aggregation(user_id, user_messages, reason)

    @service_operation_safe("用户消息聚合处理失败")
    def _process_user_aggregation(self, user_id: str, messages: List[PendingMessage], reason: str) -> None:
        """处理单个用户的消息聚合"""
        if not messages:
            return

        # 按优先级和时间排序
        sorted_messages = sorted(messages, key=lambda x: (x.priority.value, x.created_time), reverse=True)

        # 限制数量
        messages_to_aggregate = sorted_messages[:self.max_messages_per_aggregation]

        debug_utils.log_and_print(f"🔄 开始聚合用户 {user_id} 的 {len(messages_to_aggregate)} 条消息 (原因: {reason})", log_level="INFO")

        # 调用AI汇总
        aggregated_summary = self._generate_ai_summary(messages_to_aggregate)

        # 调用回调函数发送聚合消息
        if self.aggregation_callback:
            success = self.aggregation_callback(messages_to_aggregate, aggregated_summary)
            if success:
                # 移除已聚合的消息
                for msg in messages_to_aggregate:
                    self.pending_messages.pop(msg.message_id, None)
                debug_utils.log_and_print(f"✅ 用户 {user_id} 的消息聚合完成", log_level="INFO")
            else:
                debug_utils.log_and_print(f"❌ 用户 {user_id} 的消息聚合发送失败", log_level="ERROR")

    @service_operation_safe("AI摘要生成失败", return_value="消息摘要生成失败，请查看原始消息")
    def _generate_ai_summary(self, messages: List[PendingMessage]) -> str:
        """生成AI摘要"""
        if not self.app_controller:
            return "无法生成摘要：应用控制器不可用"

        llm_service = self.app_controller.get_service(ServiceNames.LLM)
        if not llm_service:
            return "无法生成摘要：LLM服务不可用"

        # 构建提示词
        message_contents = []
        for msg in messages:
            source_info = f"来源: {msg.source_type}"
            time_info = f"时间: {datetime.fromtimestamp(msg.created_time).strftime('%H:%M')}"
            content_str = json.dumps(msg.content, ensure_ascii=False, indent=2)
            message_contents.append(f"{source_info} | {time_info}\n{content_str}")

        prompt = f"""请将以下{len(messages)}条系统消息汇总成一个简洁的摘要，突出重要信息：

{"="*50}
{chr(10).join(message_contents)}
{"="*50}

要求：
1. 按重要性排序信息
2. 合并相同类型的信息
3. 突出异常或需要关注的内容
4. 控制在200字以内
5. 使用友好的语调

汇总摘要："""

        try:
            response = llm_service.simple_chat(prompt, max_tokens=1500)
            return response if response else "AI摘要生成失败"
        except Exception as e:
            debug_utils.log_and_print(f"AI摘要生成异常: {e}", log_level="ERROR")
            return f"摘要生成异常: {str(e)}"

    def _start_aggregation_timer(self) -> None:
        """启动聚合定时器"""
        def scheduled_aggregation():
            self._trigger_aggregation(reason="scheduled")
            # 重新设置定时器
            self.aggregation_timer = threading.Timer(self.aggregation_window, scheduled_aggregation)
            self.aggregation_timer.daemon = True
            self.aggregation_timer.start()

        self.aggregation_timer = threading.Timer(self.aggregation_window, scheduled_aggregation)
        self.aggregation_timer.daemon = True
        self.aggregation_timer.start()

    def _start_cleanup_timer(self) -> None:
        """启动清理定时器"""
        def cleanup():
            current_time = time.time()
            expired_messages = []

            for msg_id, msg in list(self.pending_messages.items()):
                # 清理超过24小时的消息
                if current_time - msg.created_time > 86400:
                    expired_messages.append(msg_id)

            for msg_id in expired_messages:
                self.pending_messages.pop(msg_id, None)

            if expired_messages:
                debug_utils.log_and_print(f"🧹 清理了 {len(expired_messages)} 条过期消息", log_level="INFO")

            # 重新设置清理定时器
            self.cleanup_timer = threading.Timer(3600, cleanup)  # 1小时清理一次
            self.cleanup_timer.daemon = True
            self.cleanup_timer.start()

        self.cleanup_timer = threading.Timer(3600, cleanup)
        self.cleanup_timer.daemon = True
        self.cleanup_timer.start()

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        user_stats = {}
        for msg in self.pending_messages.values():
            user_id = msg.user_id
            if user_id not in user_stats:
                user_stats[user_id] = 0
            user_stats[user_id] += 1

        return {
            "service_name": "message_aggregation",
            "status": "healthy",
            "total_pending_messages": len(self.pending_messages),
            "users_with_pending": len(user_stats),
            "user_message_stats": user_stats,
            "aggregation_window": self.aggregation_window,
            "config": {
                "max_messages_per_aggregation": self.max_messages_per_aggregation,
                "min_messages_for_aggregation": self.min_messages_for_aggregation
            }
        }

    def stop(self) -> None:
        """停止服务"""
        if self.aggregation_timer:
            self.aggregation_timer.cancel()
        if self.cleanup_timer:
            self.cleanup_timer.cancel()
        debug_utils.log_and_print("⏹️ 信息汇总服务已停止", log_level="INFO")
