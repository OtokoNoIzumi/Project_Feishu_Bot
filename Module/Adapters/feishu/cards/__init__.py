"""
飞书卡片适配器模块

基于飞书官方模板+参数方式的卡片管理架构
提供统一的卡片管理接口和扩展机制
配置驱动的卡片管理器注册系统

优化设计：
- 属地化管理：卡片类映射在本模块内部维护
- 静态映射：类型安全，重构友好
- 配置驱动：业务配置与代码结构分离
"""

from Module.Common.scripts.common import debug_utils
from .card_registry import BaseCardManager, FeishuCardRegistry
from .bilibili_cards import BilibiliCardManager
from .user_update_cards import UserUpdateCardManager
from .ads_update_cards import AdsUpdateCardManager
from .design_plan_cards import DesignPlanCardManager
from .routine_cards import RoutineCardManager
from Module.Services.constants import CardConfigKeys

# 导出主要组件
__all__ = [
    "BaseCardManager",
    "FeishuCardRegistry",
    "BilibiliCardManager",
    "UserUpdateCardManager",
    "AdsUpdateCardManager",
    "DesignPlanCardManager",
    "RoutineCardManager",
]

# ✅ 属地化：卡片类静态映射表，包含完整的配置信息
CARD_CLASS_MAPPING = {
    CardConfigKeys.USER_UPDATE: {
        "class": UserUpdateCardManager,
        "config": {
            "reply_mode": "reply",
            "card_name": "用户更新",
            "template_id": "AAqdbwJ2cflOp",
            "template_version": "1.1.0",
        },
    },
    CardConfigKeys.ADS_UPDATE: {
        "class": AdsUpdateCardManager,
        "config": {
            "reply_mode": "reply",
            "card_name": "广告更新",
            "template_id": "AAqdJvEYwMDQ3",
            "template_version": "1.0.0",
        },
    },
    CardConfigKeys.BILIBILI_VIDEO_INFO: {
        "class": BilibiliCardManager,
        "config": {
            "reply_mode": "new",
            "card_name": "B站",
            "template_id": "AAqBPdq4sxIy5",
            "template_version": "1.0.9",
        },
    },
    CardConfigKeys.DESIGN_PLAN: {
        "class": DesignPlanCardManager,
        "config": {
            "reply_mode": "reply",
            "card_name": "设计方案确认",
            "template_id": "AAqdn6SINMKfr",
            "template_version": "1.0.5",
        },
    },
    "routine_new_event": {
        "class": RoutineCardManager,
        "single_instance": True,
        "config": {"reply_mode": "reply", "card_name": "新建日常事项"},
    },
    CardConfigKeys.ROUTINE_QUICK_SELECT: {
        "class": RoutineCardManager,
        "single_instance": True,
        "config": {
            "reply_mode": "new",
            "card_name": "快速选择记录",
            "sub_business_build_method": "build_quick_select_record_elements",  # 暂无此方法
        },
    },
    CardConfigKeys.ROUTINE_QUERY: {
        "class": RoutineCardManager,
        "single_instance": True,
        "config": {
            "reply_mode": "reply",
            "card_name": "日常事项查询",
            "sub_business_build_method": "build_query_elements",
        },
    },
    CardConfigKeys.ROUTINE_DIRECT_RECORD: {
        "class": RoutineCardManager,
        "single_instance": True,
        "config": {
            "reply_mode": "reply",
            "card_name": "添加日常记录",
            "sub_business_build_method": "build_direct_record_elements",
        },
    },
}

# ✅ 操作类型到卡片配置键的映射 - 替代后端服务调用
OPERATION_TYPE_TO_CARD_CONFIG_MAPPING = {
    "update_user": "user_update",
    "update_ads": "ads_update",
}

# 创建全局卡片注册中心
card_registry = FeishuCardRegistry()

# 单例标记（常量命名风格）
_CARD_REGISTRY_INITIALIZED = False


def get_card_config_key_by_operation_type(operation_type: str):
    """根据操作类型获取卡片配置键"""
    return OPERATION_TYPE_TO_CARD_CONFIG_MAPPING.get(operation_type)


# 配置驱动的卡片管理器注册系统
def initialize_card_managers(app_controller=None, sender=None, message_router=None):
    """
    初始化并注册所有卡片管理器 - 配置驱动 + 属地化 (单例)

    Args:
        app_controller: 应用控制器实例，用于获取卡片配置
        sender: 消息发送器实例

    Returns:
        FeishuCardRegistry: 卡片注册表实例
    """
    global _CARD_REGISTRY_INITIALIZED

    # 如果已经初始化，直接返回现有实例
    if _CARD_REGISTRY_INITIALIZED:
        return card_registry

    if not app_controller:
        debug_utils.log_and_print(
            "⚠️ 缺少配置服务，跳过卡片管理器注册", log_level="WARNING"
        )
        return card_registry

    # ✅ 使用属地化配置，不再依赖外部JSON文件
    for card_type, card_static_info in CARD_CLASS_MAPPING.items():
        try:
            manager_class = card_static_info["class"]
            card_static_config = card_static_info["config"]
            single_instance = card_static_info.get("single_instance", False)

            # 创建管理器实例（传入app_controller和sender），同样作为业务终端，需要获取独立执行和调用的能力。
            manager_instance = manager_class(
                app_controller=app_controller,
                card_static_config=card_static_config,
                card_config_key=card_type,
                sender=sender,
                message_router=message_router,
                single_instance=single_instance,
            )

            # 注册管理器
            card_registry.register_manager(card_type, manager_instance)

        except Exception as e:
            debug_utils.log_and_print(
                f"❌ 注册管理器失败 {card_type}: {e}", log_level="ERROR"
            )

    # 标记为已初始化
    _CARD_REGISTRY_INITIALIZED = True
    debug_utils.log_and_print("✅ 属地化配置驱动的卡片管理器注册完成", log_level="INFO")

    return card_registry


# 便捷函数
def get_card_manager(card_type: str):
    """获取指定类型的卡片管理器"""
    return card_registry.get_manager(card_type)


def list_available_cards():
    """列出所有可用的卡片类型"""
    return list(card_registry.get_all_managers().keys())
