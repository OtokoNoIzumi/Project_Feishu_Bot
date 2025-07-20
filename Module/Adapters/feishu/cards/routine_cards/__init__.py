# -*- coding: utf-8 -*-
"""
Routine Cards Module
例行事务卡片模块

统一导出接口
"""

# 导入主协调器（重构后的RoutineCardManager）
from .main_coordinator import RoutineCardManager

# 导入子模块（可选，用于直接访问）
from .shared_utils import SharedUtils
from .query_results_card import QueryResultsCard
from .quick_select_card import QuickSelectCard
from .record_card import RecordCard


# 主要导出接口保持不变
__all__ = [
    "RoutineCardManager",  # 主要接口
    "SharedUtils",  # 共享工具
    "QueryResultsCard",  # 查询结果卡片
    "QuickSelectCard",  # 快速选择卡片
    "RecordCard",  # 快速记录卡片
]
