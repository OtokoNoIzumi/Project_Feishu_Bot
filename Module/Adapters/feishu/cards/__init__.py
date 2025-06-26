"""
飞书卡片适配器模块

基于飞书官方模板+参数方式的卡片管理架构
提供统一的卡片管理接口和扩展机制
配置驱动的卡片管理器注册系统
"""

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames
from .card_registry import BaseCardManager, FeishuCardRegistry
from .bilibili_cards import BilibiliCardManager
from .user_update_cards import UserUpdateCardManager
from .ads_update_cards import AdsUpdateCardManager
from .design_plan_cards import DesignPlanCardManager

# 导出主要组件
__all__ = [
    'BaseCardManager',
    'FeishuCardRegistry',
    'BilibiliCardManager',
    'UserUpdateCardManager',
    'AdsUpdateCardManager',
    'DesignPlanCardManager'
]

# 创建全局卡片注册中心
card_registry = FeishuCardRegistry()

# 单例标记（常量命名风格）
_CARD_REGISTRY_INITIALIZED = False


# 配置驱动的卡片管理器注册系统
def initialize_card_managers(app_controller=None, sender=None):
    """
    初始化并注册所有卡片管理器 - 配置驱动 (单例)

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
        debug_utils.log_and_print("⚠️ 缺少配置服务，跳过卡片管理器注册", log_level="WARNING")
        return card_registry

    # 从配置服务获取卡片业务映射服务
    card_mapping_service = app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
    if not card_mapping_service:
        debug_utils.log_and_print("⚠️ 卡片业务映射服务不可用，跳过注册", log_level="WARNING")
        return card_registry

    # 获取所有管理器配置
    card_definitions = card_mapping_service.get_all_definition()

    for card_type, card_definition in card_definitions.items():
        try:
            # 动态导入管理器类
            module_path = card_definition.get('module_path')
            class_name = card_definition.get('class_name')

            if not module_path or not class_name:
                debug_utils.log_and_print(f"⚠️ 卡片定义不完整: {card_type}", log_level="WARNING")
                continue

            # 导入模块和类
            module = __import__(module_path, fromlist=[class_name])
            manager_class = getattr(module, class_name)

            # 创建管理器实例（传入app_controller和sender）
            manager_instance = manager_class(
                app_controller=app_controller,
                card_info=card_definition,
                card_config_key=card_type,
                sender=sender
            )

            # 注册管理器
            card_registry.register_manager(card_type, manager_instance)

        except Exception as e:
            debug_utils.log_and_print(f"❌ 注册管理器失败 {card_type}: {e}", log_level="ERROR")

    # 标记为已初始化
    _CARD_REGISTRY_INITIALIZED = True
    debug_utils.log_and_print("✅ 配置驱动的卡片管理器注册完成", log_level="INFO")

    return card_registry


# 便捷函数
def get_card_manager(card_type: str):
    """获取指定类型的卡片管理器"""
    return card_registry.get_manager(card_type)


def list_available_cards():
    """列出所有可用的卡片类型"""
    return list(card_registry.get_all_managers().keys())
