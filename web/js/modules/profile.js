/**
 * Profile 模块
 * 
 * 处理用户档案的加载、编辑、AI 分析和保存
 * 
 * 核心功能：
 * 1. 从后端加载 Profile（含动态指标：体重/身高）
 * 2. AI 分析生成建议（暂存值），支持对比和还原
 * 3. user_info 的 diff 展示
 * 4. 聊天窗口集成（档案沟通模式）
 */

const ProfileModule = {
    // 状态
    serverProfile: null,      // 后端加载的原始 Profile
    pendingProfile: null,     // 暂存的修改（analyze 返回或手动编辑）
    dynamicMetrics: null,     // 动态指标（weight_kg, height_cm）
    isLoading: false,
    lastAnalyzeResponse: null,

    // 初始化
    async init() {
        await this.loadFromServer();
    },

    // ========== 数据加载 ==========

    async loadFromServer() {
        this.isLoading = true;
        try {
            const response = await API.getProfile();
            // response 是 ProfileView: { ...settings, current_weight_kg, height_cm }
            // 后端将 settings 打平到顶层，并注入 current_weight_kg, height_cm
            this.serverProfile = response;
            this.dynamicMetrics = {
                weight_kg: response.current_weight_kg,  // 后端字段名是 current_weight_kg
                height_cm: response.height_cm,
            };
            this.pendingProfile = null; // 清空暂存
            return this.serverProfile;
        } catch (e) {
            console.warn('[Profile] Failed to load from server:', e);
            // 返回默认值
            this.serverProfile = this.getDefaultProfile();
            this.dynamicMetrics = { weight_kg: null, height_cm: null };
            return this.serverProfile;
        } finally {
            this.isLoading = false;
        }
    },

    getDefaultProfile() {
        return {
            gender: null,  // 前端不使用后端默认值
            age: 25,
            activity_level: 'sedentary',
            timezone: 'Asia/Shanghai',
            diet: {
                energy_unit: 'kJ',
                goal: 'fat_loss',
                daily_energy_kj_target: null,
                protein_g_target: null,
                fat_g_target: null,
                carbs_g_target: null,
                sodium_mg_target: null,
            },
            keep: {
                weight_kg_target: null,
                body_fat_pct_target: null,
                dimensions_target: {},
            },
            user_info: null,
            estimated_months: null,
        };
    },

    // ========== 状态查询 ==========

    /**
     * 获取当前显示的 Profile（优先暂存，否则服务端）
     */
    getCurrentProfile() {
        return this.pendingProfile || this.serverProfile || this.getDefaultProfile();
    },

    /**
     * 检查是否可以进行 AI 分析
     */
    canAnalyze() {
        const p = this.getCurrentProfile();
        const missing = [];
        if (!p.gender) missing.push('性别');
        if (!p.age) missing.push('年龄');

        // 优先检查暂存的身体指标 (前端输入的)，如果没有再检查服务端的
        const metrics = this.pendingMetrics || this.dynamicMetrics || {};
        if (!metrics.weight_kg) missing.push('体重');
        if (!metrics.height_cm) missing.push('身高');

        return { canAnalyze: missing.length === 0, missing };
    },

    /**
     * 检查是否有未保存的修改（包括 Profile 和身体指标）
     */
    hasChanges() {
        const profileChanged = this.pendingProfile &&
            JSON.stringify(this.pendingProfile) !== JSON.stringify(this.serverProfile);
        const metricsChanged = this.pendingMetrics &&
            JSON.stringify(this.pendingMetrics) !== JSON.stringify(this.dynamicMetrics);
        return profileChanged || metricsChanged;
    },

    // ========== AI 分析 ==========

    /**
     * 执行 AI 分析
     * @param {string} userNote - 用户输入
     * @param {number} targetMonths - 目标月份
     */
    async analyze(userNote, targetMonths = null) {
        const { canAnalyze, missing } = this.canAnalyze();
        if (!canAnalyze) {
            return {
                success: false,
                error: `请先完善以下信息：${missing.join('、')}`,
            };
        }

        try {
            // 传递当前编辑的 Profile 和身体指标（所见即所得）
            const currentProfile = this.getCurrentProfile();
            const currentMetrics = this.pendingMetrics || this.dynamicMetrics || {};
            const metricsOverride = {
                height_cm: currentMetrics.height_cm,
                weight_kg: currentMetrics.weight_kg,
            };
            const response = await API.analyzeProfile(userNote, targetMonths, false, currentProfile, metricsOverride);
            this.lastAnalyzeResponse = response;
            this.pendingProfile = response.suggested_profile;
            return {
                success: true,
                advice: response.advice,
                estimatedMonths: response.estimated_months,
                profile: response.suggested_profile,
            };
        } catch (e) {
            return {
                success: false,
                error: e.message || '分析失败',
            };
        }
    },

    // ========== 保存 ==========

    async saveToServer() {
        const profile = this.getCurrentProfile();
        try {
            // 1. 保存 Profile
            await API.saveProfile(profile);

            // 2. 保存身体指标到 Keep（如果有修改）
            if (this.pendingMetrics) {
                await this.saveMetricsToKeep();
            }

            this.serverProfile = JSON.parse(JSON.stringify(profile));
            this.pendingProfile = null;
            this.dynamicMetrics = this.pendingMetrics ? { ...this.pendingMetrics } : this.dynamicMetrics;
            this.pendingMetrics = null;
            return { success: true };
        } catch (e) {
            return { success: false, error: e.message };
        }
    },

    /**
     * 保存身体指标到 Keep
     */
    async saveMetricsToKeep() {
        const metrics = this.pendingMetrics || {};

        // 如果身高有变化，保存到 dimensions
        if (metrics.height_cm !== this.dynamicMetrics?.height_cm && metrics.height_cm) {
            await API.saveKeep({ height: metrics.height_cm }, 'dimensions');
        }

        // 如果体重有变化，保存到 scale
        if (metrics.weight_kg !== this.dynamicMetrics?.weight_kg && metrics.weight_kg) {
            await API.saveKeep({ weight_kg: metrics.weight_kg }, 'scale');
        }
    },

    // ========== 身体指标编辑 ==========

    pendingMetrics: null,

    /**
     * 更新身体指标暂存值
     */
    updateMetric(key, value) {
        if (!this.pendingMetrics) {
            this.pendingMetrics = { ...this.dynamicMetrics };
        }
        this.pendingMetrics[key] = value;
    },

    /**
     * 还原身体指标
     */
    revertMetric(key) {
        if (this.pendingMetrics && this.dynamicMetrics) {
            this.pendingMetrics[key] = this.dynamicMetrics[key];
        }
    },

    // ========== 还原 ==========

    /**
     * 一键还原所有修改
     */
    revertAll() {
        this.pendingProfile = null;
        this.pendingMetrics = null;
    },

    /**
     * 局部还原某个字段
     * @param {string} fieldPath - 字段路径，如 'diet.daily_energy_kj_target'
     */
    revertField(fieldPath) {
        if (!this.pendingProfile || !this.serverProfile) return;

        const parts = fieldPath.split('.');
        let pendingRef = this.pendingProfile;
        let serverRef = this.serverProfile;

        // 遍历到父级
        for (let i = 0; i < parts.length - 1; i++) {
            if (!pendingRef[parts[i]]) pendingRef[parts[i]] = {};
            pendingRef = pendingRef[parts[i]];
            serverRef = serverRef?.[parts[i]] || {};
        }

        const lastKey = parts[parts.length - 1];
        pendingRef[lastKey] = serverRef[lastKey];
    },

    /**
     * 更新暂存值中的某个字段
     * @param {string} fieldPath - 字段路径
     * @param {any} value - 新值
     */
    updateField(fieldPath, value) {
        // 如果还没有暂存，先创建一份 copy
        if (!this.pendingProfile) {
            this.pendingProfile = JSON.parse(JSON.stringify(this.serverProfile || this.getDefaultProfile()));
        }

        const parts = fieldPath.split('.');
        let ref = this.pendingProfile;

        for (let i = 0; i < parts.length - 1; i++) {
            if (!ref[parts[i]]) ref[parts[i]] = {};
            ref = ref[parts[i]];
        }

        ref[parts[parts.length - 1]] = value;
    },

    // ========== Diff 工具 ==========

    /**
     * 获取字段的变化状态
     * @param {string} fieldPath - 字段路径
     * @returns {{ hasChange: boolean, original: any, current: any }}
     */
    getFieldChange(fieldPath) {
        // 处理身体指标字段
        if (fieldPath.startsWith('_metrics.')) {
            const key = fieldPath.replace('_metrics.', '');
            const original = this.dynamicMetrics?.[key];
            const pending = this.pendingMetrics?.[key];
            const current = pending !== undefined ? pending : original;
            return {
                hasChange: pending !== undefined && pending !== original,
                original,
                current,
            };
        }

        const parts = fieldPath.split('.');

        let serverVal = this.serverProfile;
        let pendingVal = this.pendingProfile;

        for (const part of parts) {
            serverVal = serverVal?.[part];
            pendingVal = pendingVal?.[part];
        }

        const current = pendingVal !== undefined ? pendingVal : serverVal;
        const original = serverVal;

        return {
            hasChange: pendingVal !== undefined && JSON.stringify(pendingVal) !== JSON.stringify(serverVal),
            original,
            current,
        };
    },

    /**
     * 生成 user_info 的精确 Diff (Character Level LCS)
     */
    getUserInfoDiff() {
        const original = this.serverProfile?.user_info || '';
        const current = this.pendingProfile?.user_info || this.serverProfile?.user_info || '';

        if (original === current) {
            return { hasDiff: false, original, current };
        }

        // LCS 算法实现字符级 Diff
        const O = original.split('');
        const N = current.split('');
        const matrix = Array(O.length + 1).fill(null).map(() => Array(N.length + 1).fill(0));

        for (let i = 1; i <= O.length; i++) {
            for (let j = 1; j <= N.length; j++) {
                if (O[i - 1] === N[j - 1]) {
                    matrix[i][j] = matrix[i - 1][j - 1] + 1;
                } else {
                    matrix[i][j] = Math.max(matrix[i - 1][j], matrix[i][j - 1]);
                }
            }
        }

        let i = O.length, j = N.length;
        const diff = [];

        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && O[i - 1] === N[j - 1]) {
                diff.unshift({ type: 'equal', value: O[i - 1] });
                i--; j--;
            } else if (j > 0 && (i === 0 || matrix[i][j - 1] >= matrix[i - 1][j])) {
                diff.unshift({ type: 'add', value: N[j - 1] });
                j--;
            } else {
                diff.unshift({ type: 'remove', value: O[i - 1] });
                i--;
            }
        }

        // 合并相邻的同类型块
        const merged = [];
        if (diff.length > 0) {
            let last = { ...diff[0] };
            for (let k = 1; k < diff.length; k++) {
                if (diff[k].type === last.type) {
                    last.value += diff[k].value;
                } else {
                    merged.push(last);
                    last = { ...diff[k] };
                }
            }
            merged.push(last);
        }

        return { hasDiff: true, original, current, diff: merged };
    },

    // ========== 辅助方法 ==========

    renderGenderOptions(selected) {
        // 前端不使用后端默认值，未选中时 selected 为 null
        const options = [
            { value: '', label: '请选择' },
            { value: 'female', label: '女' },
            { value: 'male', label: '男' },
        ];
        return options.map(o =>
            `<option value="${o.value}" ${o.value === (selected || '') ? 'selected' : ''}>${o.label}</option>`
        ).join('');
    },

    renderActivityLevelOptions(selected) {
        const options = [
            { value: 'sedentary', label: '久坐（几乎不运动）' },
            { value: 'light', label: '轻度活动（每周1-3次）' },
            { value: 'moderate', label: '中度活动（每周3-5次）' },
            { value: 'active', label: '高度活动（每周6-7次）' },
            { value: 'very_active', label: '非常活跃（体力劳动/专业运动）' },
        ];
        return options.map(o =>
            `<option value="${o.value}" ${o.value === (selected || 'sedentary') ? 'selected' : ''}>${o.label}</option>`
        ).join('');
    },

    renderDietGoalOptions(selected) {
        const options = [
            { value: 'fat_loss', label: '减脂' },
            { value: 'maintain', label: '维持' },
            { value: 'muscle_gain', label: '增肌' },
            { value: 'health', label: '健康' },
        ];
        return options.map(o =>
            `<option value="${o.value}" ${o.value === (selected || 'fat_loss') ? 'selected' : ''}>${o.label}</option>`
        ).join('');
    },

    renderTimezoneOptions(selected) {
        const zones = [
            { value: 'Asia/Shanghai', label: '中国' },
            { value: 'Asia/Tokyo', label: '日本' },
            { value: 'Asia/Singapore', label: '新加坡' },
            { value: 'Europe/London', label: '英国' },
            { value: 'America/Los_Angeles', label: '美国西海岸' },
            { value: 'America/New_York', label: '美国东海岸' },
        ];
        return zones.map(z =>
            `<option value="${z.value}" ${z.value === selected ? 'selected' : ''}>${z.label}</option>`
        ).join('');
    },

    // ========== 兼容层（供 Dashboard 调用） ==========

    // 原有 ProfileUtils 的方法
    loadFromStorage() {
        // 兼容：从 localStorage 读取（用于离线）
        try {
            const raw = localStorage.getItem('dk_profile_v1');
            if (!raw) return this.getDefaultProfile();
            return JSON.parse(raw);
        } catch (e) {
            return this.getDefaultProfile();
        }
    },

    saveToStorage(profile) {
        localStorage.setItem('dk_profile_v1', JSON.stringify(profile));
    },
};

// 保持向后兼容
const ProfileUtils = ProfileModule;

// 挂载到全局
window.ProfileModule = ProfileModule;
window.ProfileUtils = ProfileUtils;
