/**
 * 能量转换工具函数
 * 
 * 从 dashboard.js 抽取的纯工具函数
 * 这些函数无副作用，可独立测试
 */

const EnergyUtils = {
    // kcal -> kJ
    kcalToKJ(kcal) {
        return (Number(kcal) || 0) * 4.184;
    },

    // kJ -> kcal
    kJToKcal(kj) {
        return (Number(kj) || 0) / 4.184;
    },

    // 宏量 -> kcal（P/C=4, F=9）
    macrosToKcal(proteinG, fatG, carbsG) {
        const p = Number(proteinG) || 0;
        const f = Number(fatG) || 0;
        const c = Number(carbsG) || 0;
        return p * 4 + f * 9 + c * 4;
    },

    // 从宏量计算能量并格式化显示（返回 String）
    formatEnergyFromMacros(proteinG, fatG, carbsG, unit) {
        const kcal = this.macrosToKcal(proteinG, fatG, carbsG);
        if (unit === 'kcal') {
            return String(Math.round(kcal));
        }
        // KJ 保留1位小数，避免 520+410=930 的视觉误差
        const kj = this.kcalToKJ(kcal);
        return (Math.round(kj * 10) / 10).toFixed(1);
    },

    // 计算三大宏量的能量占比
    getMacroEnergyRatio(proteinG, fatG, carbsG) {
        const p = (Number(proteinG) || 0) * 4;
        const f = (Number(fatG) || 0) * 9;
        const c = (Number(carbsG) || 0) * 4;
        const t = p + f + c;
        if (t <= 0) {
            return { total_kcal: 0, p_pct: 0, f_pct: 0, c_pct: 0 };
        }
        return {
            total_kcal: t,
            p_pct: Math.round((p / t) * 100),
            f_pct: Math.round((f / t) * 100),
            c_pct: Math.round((c / t) * 100),
        };
    },

    /**
     * Standardized rounding logic for different fields.
     */
    round(value, precision) {
        if (typeof value !== 'number') return value;
        const scale = Math.pow(10, precision);
        return Math.round(value * scale) / scale;
    },

    safeRound(value, precision) {
        return this.round(Number(value) || 0, precision);
    },

    // Apply standard precision rules based on field name
    // Enforces: 
    // - Energy/Sodium: 0 or 1 decimal (context dependent, usually 1 for KJ)
    // - Macros (P/F/C/Fib): 1 decimal (standard) -> Updated to 2 for High Precision calculation 
    // - Weight: 1 decimal
    applyRoundingTo(obj, fieldMap) {
        if (!obj) return;
        // Standard Precision Map (Default)
        // Can be overridden by fieldMap
        const defaultMap = {
            'weight_g': 1, 'weight': 1,
            'energy_kj': 1, 'energy': 1,
            'protein_g': 2, 'protein': 2,
            'fat_g': 2, 'fat': 2,
            'carbs_g': 2, 'carb': 2, 'carbs': 2,
            'fiber_g': 2, 'fiber': 2,
            'sodium_mg': 1, 'sodium': 1,
        };

        const map = { ...defaultMap, ...fieldMap };

        for (const key in obj) {
            if (map.hasOwnProperty(key)) {
                obj[key] = this.round(obj[key], map[key]);
            }
        }
    }
};

// 挂载到全局，供其他模块使用
window.EnergyUtils = EnergyUtils;
