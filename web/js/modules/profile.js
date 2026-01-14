/**
 * Profile 工具模块
 * 
 * 从 dashboard.js 抽取的 Profile 相关纯数据函数
 * 这些函数无副作用，不依赖 Dashboard 其他方法
 */

const ProfileUtils = {
    // 默认 Profile 配置
    getDefaultProfile() {
        return {
            timezone: 'Asia/Shanghai',
            diet: {
                energy_unit: 'kJ',
                goal: 'fat_loss',
                daily_energy_kj_target: 6273,
                protein_g_target: 110,
                fat_g_target: 50,
                carbs_g_target: 150,
                sodium_mg_target: 2000,
            },
            keep: {
                weight_kg_target: 0,
                body_fat_pct_target: 0,
                dimensions_cm_target: {
                    chest_cm: 0,
                    waist_cm: 0,
                    hips_cm: 0,
                }
            }
        };
    },

    // 时区选项
    renderTimezoneOptions(selected) {
        const zones = [
            { value: 'Asia/Shanghai', label: '中国（Asia/Shanghai）' },
            { value: 'Asia/Hong_Kong', label: '中国香港（Asia/Hong_Kong）' },
            { value: 'Asia/Taipei', label: '中国台北（Asia/Taipei）' },
            { value: 'Asia/Tokyo', label: '日本（Asia/Tokyo）' },
            { value: 'Asia/Singapore', label: '新加坡（Asia/Singapore）' },
            { value: 'Europe/London', label: '英国（Europe/London）' },
            { value: 'Europe/Berlin', label: '德国（Europe/Berlin）' },
            { value: 'America/Los_Angeles', label: '美国西海岸（America/Los_Angeles）' },
            { value: 'America/New_York', label: '美国东海岸（America/New_York）' },
        ];
        return zones.map(z => `<option value="${z.value}" ${z.value === selected ? 'selected' : ''}>${z.label}</option>`).join('');
    },

    // 饮食目标选项
    renderDietGoalOptions(selected) {
        const goals = [
            { value: 'fat_loss', label: '减脂' },
            { value: 'maintain', label: '维持' },
            { value: 'muscle_gain', label: '增肌' },
            { value: 'health', label: '健康' },
        ];
        const sel = selected || 'fat_loss';
        return goals.map(g => `<option value="${g.value}" ${g.value === sel ? 'selected' : ''}>${g.label}</option>`).join('');
    },

    // 从 localStorage 加载 Profile
    loadFromStorage() {
        try {
            const raw = localStorage.getItem('dk_profile_v1');
            if (!raw) return this.getDefaultProfile();
            const parsed = JSON.parse(raw);
            return Object.assign(this.getDefaultProfile(), parsed || {});
        } catch (e) {
            return this.getDefaultProfile();
        }
    },

    // 保存 Profile 到 localStorage
    saveToStorage(profile) {
        localStorage.setItem('dk_profile_v1', JSON.stringify(profile));
    },
};

// 挂载到全局
window.ProfileUtils = ProfileUtils;
