"""
飞书适配器工具函数

集中管理飞书适配器层的通用工具函数和辅助方法
"""

import json
import pprint
import datetime
from typing import Dict, Any

from Module.Common.scripts.common import debug_utils
from Module.Application.app_utils import custom_serializer

# P2ImMessageReceiveV1对象调试开关 - 开发调试用
DEBUG_P2IM_OBJECTS = False  # 设置为True启用详细调试输出


def extract_timestamp(data) -> datetime.datetime:
    """
    提取通用的上下文数据（时间戳和用户名）

    Args:
        data: 飞书事件数据
        use_event_time: 是否使用事件时间（True: 消息/菜单事件时间, False: 当前时间用于卡片）

    Returns:
        timestamp: 时间戳
    """
    # 消息事件使用 message.create_time，菜单事件使用 header.create_time
    if hasattr(data, 'event') and hasattr(data.event, 'message') and hasattr(data.event.message, 'create_time'):
        # 消息事件
        create_time_ms = int(data.event.message.create_time)
    elif hasattr(data, 'header') and hasattr(data.header, 'create_time'):
        # 菜单事件
        create_time_ms = int(data.header.create_time)
    else:
        # 回退到当前时间
        create_time_ms = int(datetime.datetime.now().timestamp() * 1000)

    timestamp = datetime.datetime.fromtimestamp(create_time_ms / 1000)

    return timestamp


def debug_p2im_object(data, object_type: str = "P2ImMessageReceiveV1"):
    """
    调试P2ImMessageReceiveV1对象的详细信息输出

    Args:
        data: 需要调试的对象
        object_type: 对象类型名称（用于日志标识）
    """
    if not DEBUG_P2IM_OBJECTS:
        return

    debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (JSON序列化):", log_level="DEBUG")
    try:
        serializable_data = custom_serializer(data)
        json_output = json.dumps(serializable_data, indent=2, ensure_ascii=False)
        debug_utils.log_and_print(json_output, log_level="DEBUG")
        debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (pprint):", log_level="DEBUG")
        dict_representation = custom_serializer(data)
        pretty_output = pprint.pformat(dict_representation, indent=2, width=120)
        debug_utils.log_and_print(pretty_output, log_level="DEBUG")
    except Exception as e:
        debug_utils.log_and_print(f"  - 序列化失败: {e}", log_level="ERROR")
        debug_utils.log_and_print(f"  - 尝试使用 repr(): {repr(data)}", log_level="DEBUG")


def debug_parent_id_analysis(data):
    """
    分析并调试parent_id相关信息

    Args:
        data: 需要分析的消息对象
    """
    if not DEBUG_P2IM_OBJECTS:
        return

    # 特别关注回复消息的关键字段 parent_id
    if hasattr(data, 'event') and hasattr(data.event, 'message') and hasattr(data.event.message, 'parent_id'):
        parent_id = data.event.message.parent_id
        if parent_id:
            debug_utils.log_and_print(f"  - 关键信息: 此消息为回复消息, parent_id = {parent_id}", log_level="INFO")
        else:
            debug_utils.log_and_print("  - 关键信息: 此消息非回复消息 (parent_id is None or empty)", log_level="DEBUG")
    else:
        debug_utils.log_and_print("  - 关键信息: 未找到 parent_id 属性路径", log_level="DEBUG")


def noop_debug(*args, **kwargs):
    """空操作调试函数，用于禁用调试时的占位符"""
    pass


def create_debug_functions():
    """
    创建调试函数字典，用于注入到处理器中

    Returns:
        dict: 包含调试函数的字典
    """
    return {
        'debug_p2im_object': debug_p2im_object,
        'debug_parent_id_analysis': debug_parent_id_analysis
    }


# 便捷导出
__all__ = [
    'extract_timestamp',
    'debug_p2im_object',
    'debug_parent_id_analysis',
    'noop_debug',
    'create_debug_functions',
    'DEBUG_P2IM_OBJECTS'
]