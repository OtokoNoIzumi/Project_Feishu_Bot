"""
能量单位换算工具（原子能力）

约定：
- 后端逻辑口径优先 KJ
- 但部分数据源（如 Keep）原生使用 Kcal，需要统一换算
"""

from __future__ import annotations


KCAL_TO_KJ_FACTOR = 4.184


def kcal_to_kj(kcal: float) -> float:
    return round(float(kcal) * KCAL_TO_KJ_FACTOR, 4)


def kj_to_kcal(kj: float) -> float:
    return round(float(kj) / KCAL_TO_KJ_FACTOR, 4)

