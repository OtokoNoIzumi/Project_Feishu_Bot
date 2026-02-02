/**
 * 卡片显示工具函数
 * 
 * 统一生成卡片标题和副标题的逻辑，供各模块调用
 */
const CardDisplayUtils = {
    // 餐时映射表
    MEAL_TIME_MAP: {
        'snack': '加餐',
        'breakfast': '早餐',
        'lunch': '午餐',
        'dinner': '晚餐'
    },

    /**
     * 生成 Diet 卡片的标题
     * 格式：{餐时} {第一道菜名}等{N}个
     * 例如："早餐 燕麦脱脂奶等3个"
     * 
     * @param {Object} parsedData - 解析后的数据 (来自 ParserModule)
     * @returns {string} 标题
     */
    generateDietTitle(parsedData) {
        if (!parsedData || parsedData.type !== 'diet') return '';

        const mealTime = this.MEAL_TIME_MAP[parsedData.summary?.dietTime] || '饮食';
        const dishes = parsedData.dishes || [];

        if (dishes.length === 0) {
            return mealTime;
        } else if (dishes.length === 1) {
            return `${mealTime} ${dishes[0].name || '未命名'}`;
        } else {
            return `${mealTime} ${dishes[0].name || '未命名'}等${dishes.length}个`;
        }
    },

    /**
     * 生成 Diet 卡片的副标题
     * 格式：{时间} · {能量} · {总重}
     * 例如："今天 08:30 · 436kJ · 120g"
     * 
     * @param {Object} options
     * @param {Date|string} options.timestamp - 时间戳
     * @param {number} options.energyKJ - 能量 (kJ)
     * @param {number} options.totalWeight - 总重量 (g)
     * @param {string} options.unit - 能量单位 ('kJ' 或 'kcal')
     * @returns {string} 副标题
     */
    generateDietSubtitle({ timestamp, energyKJ, totalWeight, unit = 'kJ' }) {
        const parts = [];

        // 时间
        if (timestamp && window.DateFormatter) {
            parts.push(window.DateFormatter.formatSmart(timestamp));
        }

        // 能量
        if (typeof energyKJ === 'number') {
            const energyVal = unit === 'kcal' ? energyKJ / 4.184 : energyKJ;
            parts.push(`${Math.round(energyVal)}${unit}`);
        }

        // 总重
        if (totalWeight && totalWeight > 0) {
            parts.push(`${Math.round(totalWeight)}g`);
        }

        return parts.join(' · ');
    },

    /**
     * 生成 Keep 卡片的标题
     * 
     * @param {Object} parsedData - 解析后的数据
     * @returns {string} 标题
     */
    generateKeepTitle(parsedData) {
        if (!parsedData || parsedData.type !== 'keep') return '';

        const scaleEvents = parsedData.scaleEvents || [];
        const sleepEvents = parsedData.sleepEvents || [];
        const bodyMeasureEvents = parsedData.bodyMeasureEvents || [];

        if (scaleEvents.length > 0 && scaleEvents[0].weight_kg) {
            return `体重 ${scaleEvents[0].weight_kg}kg`;
        }

        const count = scaleEvents.length + sleepEvents.length + bodyMeasureEvents.length;
        return count > 0 ? `Keep记录 ${count}项` : 'Keep记录';
    },

    /**
     * 统一入口：根据 parsedData 生成标题
     * 
     * @param {Object} parsedData
     * @returns {string}
     */
    generateTitle(parsedData) {
        if (!parsedData) return '';
        if (parsedData.type === 'diet') return this.generateDietTitle(parsedData);
        if (parsedData.type === 'keep') return this.generateKeepTitle(parsedData);
        return '';
    },

    /**
     * 从 rawResult (后端结构) 生成标题
     * 适用于 Sidebar 等直接拿 raw_result 的场景
     * 
     * @param {Object} rawData - 后端原始数据 (含 meal_summary, dishes 等)
     * @returns {string}
     */
    generateDietTitleFromRaw(rawData) {
        if (!rawData || !rawData.meal_summary) return '';

        const mealTime = this.MEAL_TIME_MAP[rawData.meal_summary.diet_time] || '饮食';
        const dishes = rawData.dishes || [];

        if (dishes.length === 0) {
            return mealTime;
        } else if (dishes.length === 1) {
            return `${mealTime} ${dishes[0].standard_name || '未命名'}`;
        } else {
            return `${mealTime} ${dishes[0].standard_name || '未命名'}等${dishes.length}个`;
        }
    },

    /**
     * 从 rawResult 生成副标题
     * 
     * @param {Object} rawData - 后端原始数据
     * @param {Date|string} timestamp - 时间戳
     * @param {string} unit - 能量单位
     * @returns {string}
     */
    generateDietSubtitleFromRaw(rawData, timestamp, unit = 'kJ') {
        if (!rawData || !rawData.meal_summary) return '';

        const energyKJ = rawData.meal_summary.total_energy_kj || 0;

        // 计算总重
        let totalWeight = rawData.meal_summary.net_weight_g || 0;
        if (!totalWeight && rawData.dishes) {
            totalWeight = rawData.dishes.reduce((sum, dish) => {
                if (dish.weight_g) return sum + dish.weight_g;
                if (dish.ingredients && Array.isArray(dish.ingredients)) {
                    return sum + dish.ingredients.reduce((iSum, ing) => iSum + (ing.weight_g || 0), 0);
                }
                return sum;
            }, 0);
        }

        return this.generateDietSubtitle({
            timestamp,
            energyKJ,
            totalWeight,
            unit
        });
    }
};

window.CardDisplayUtils = CardDisplayUtils;
