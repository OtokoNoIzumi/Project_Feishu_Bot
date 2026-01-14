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

    // 从宏量计算能量并格式化显示
    formatEnergyFromMacros(proteinG, fatG, carbsG, unit) {
        const kcal = this.macrosToKcal(proteinG, fatG, carbsG);
        if (unit === 'kcal') {
            return Math.round(kcal);
        }
        return Math.round(this.kcalToKJ(kcal));
    },

    // 计算三大宏量的能量占比
    getMacroEnergyRatio(proteinG, fatG, carbsG) {
        const pKcal = (Number(proteinG) || 0) * 4;
        const fKcal = (Number(fatG) || 0) * 9;
        const cKcal = (Number(carbsG) || 0) * 4;
        const total = pKcal + fKcal + cKcal;
        if (total === 0) return { protein: 0, fat: 0, carbs: 0 };
        return {
            protein: Math.round((pKcal / total) * 100),
            fat: Math.round((fKcal / total) * 100),
            carbs: Math.round((cKcal / total) * 100),
        };
    },
};

// 挂载到全局，供其他模块使用
window.EnergyUtils = EnergyUtils;
