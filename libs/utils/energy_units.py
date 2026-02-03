"""
能量单位换算工具（原子能力）

约定：
- 后端逻辑口径优先 KJ
- 但部分数据源（如 Keep）原生使用 Kcal，需要统一换算
"""

from __future__ import annotations


KCAL_TO_KJ_FACTOR = 4.184


def kcal_to_kj(kcal: float) -> float:
    """Convert kilocalories to kilojoules."""
    return round(float(kcal) * KCAL_TO_KJ_FACTOR, 4)


def kj_to_kcal(kj: float) -> float:
    """Convert kilojoules to kilocalories."""
    return round(float(kj) / KCAL_TO_KJ_FACTOR, 4)


def macro_energy_kj(protein_g: float, fat_g: float, carbs_g: float) -> float:
    """Calculate energy from macros (4-9-4 rule in KJ)."""
    return (protein_g * 4 + carbs_g * 4 + fat_g * 9) * KCAL_TO_KJ_FACTOR
