"""
飞书卡片适配器模块

基于飞书官方模板+参数方式的卡片管理架构
提供统一的卡片管理接口和扩展机制
"""

from .base_card_manager import BaseCardManager, FeishuCardRegistry
from .bilibili_cards import BilibiliCardManager

# 导出主要组件
__all__ = [
    'BaseCardManager',
    'FeishuCardRegistry',
    'BilibiliCardManager'
]

# 创建全局卡片注册中心
card_registry = FeishuCardRegistry()

# 自动注册可用的卡片管理器
def initialize_card_managers():
    """初始化并注册所有卡片管理器"""
    # 注册B站卡片管理器
    bili_manager = BilibiliCardManager()
    card_registry.register_manager("bilibili", bili_manager)

    # 后续可以继续添加其他卡片管理器
    # music_manager = MusicCardManager()
    # card_registry.register_manager("music", music_manager)

    return card_registry

# 便捷函数
def get_card_manager(card_type: str):
    """获取指定类型的卡片管理器"""
    return card_registry.get_manager(card_type)

def list_available_cards():
    """列出所有可用的卡片类型"""
    return card_registry.list_managers()