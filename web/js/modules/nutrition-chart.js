/**
 * Nutrition Chart Module
 *
 * 使用 ECharts 显示营养摄入可视化图表
 * 核心设计：以"目标完成百分比"为统一尺度，使所有营养素可比较
 */
const NutritionChartModule = {
    chartInstance: null,
    todaySummary: null,   // 今日已摄入（从 analyze 响应获取）
    userTarget: null,     // 用户目标（从 analyze 响应或 profile 获取）

    // 颜色定义 - Warm Notebook Theme
    colors: {
        thisMeal: '#d97757',     // Terracotta (Accent)
        todayIntake: '#6b8e23',  // Olive Green (Natural)
        target: '#cd853f',       // Peru (Warning/Target)
        background: 'rgba(92, 85, 78, 0.03)', // Subtle sketch area
    },

    /**
     * 初始化图表数据（从 analyze 响应获取 context）
     */
    setContext(context) {
        if (!context) return;
        this.todaySummary = context.today_so_far || {};
        this.userTarget = context.user_target || {};
    },

    /**
     * 渲染图表
     */
    render(containerId, currentTotals, energyUnit) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // ECharts 未加载
        if (typeof echarts === 'undefined') {
            container.innerHTML = '<div class="nutrition-chart-fallback">图表加载中...</div>';
            return;
        }

        // 销毁旧实例
        if (this.chartInstance) {
            this.chartInstance.dispose();
        }

        // 确保容器高度
        container.style.height = '220px';

        const chart = echarts.init(container, null, { renderer: 'canvas' });
        this.chartInstance = chart;

        const option = this.buildOption(currentTotals, energyUnit);
        chart.setOption(option);

        // 响应窗口大小变化
        const resizeHandler = () => {
            if (this.chartInstance) this.chartInstance.resize();
        };
        window.removeEventListener('resize', resizeHandler);
        window.addEventListener('resize', resizeHandler);
    },

    /**
     * 更新本次分析数据（checkbox/数值变化时）
     */
    updateCurrentMeal(currentTotals, energyUnit) {
        if (!this.chartInstance) return;
        const option = this.buildOption(currentTotals, energyUnit);
        this.chartInstance.setOption(option, true);
    },

    /**
     * 构建 ECharts 配置 - 水平条形图
     */
    buildOption(currentTotals, energyUnit) {
        // 1. 获取构建好的数据
        const data = this.buildPercentageData(currentTotals, energyUnit);

        // 2. 确保这里的顺序与 buildPercentageData 中 nutrients 的顺序完全一致（倒序，因为 ECharts Y轴从下到上）
        // nutrients 是：能量, 蛋白质, 脂肪, 碳水, 纤维, 钠
        // 为了让"能量"显示在最上面，categories 数组应该是反过来的：
        // [钠, 纤维, 碳水, 脂肪, 蛋白质, 能量]
        // 对应的 data.todayPercent 也必须反转！

        const categories = ['钠', '纤维', '碳水', '脂肪', '蛋白质', '能量'];

        // 翻转数据数组以匹配 Y 轴从下到上的渲染顺序
        const todayData = [...data.todayPercent].reverse();
        const thisMealData = [...data.thisMealPercent].reverse();

        const stackMax = Math.max(
            100,
            ...todayData.map((v, i) => (Number(v) || 0) + (Number(thisMealData[i]) || 0))
        );
        const axisMax = Math.max(120, Math.ceil(stackMax / 20) * 20);

        return {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                backgroundColor: '#fdfbf7', // Paper background
                borderColor: '#d97757',     // Accent border
                borderWidth: 1,
                padding: [12, 16],
                textStyle: { color: '#4a3e35', fontSize: 13, fontFamily: 'Lora' }, // Ink text
                extraCssText: 'box-shadow: 0 4px 12px rgba(74, 62, 53, 0.15); border-radius: 8px;',
                formatter: (params) => {
                    // params[0] 是第一个系列的数据
                    const index = params[0].dataIndex;
                    // 因为数据翻转了，所以要用 categories[index] 获取正确的名称
                    const catName = categories[index];
                    const info = data.details[catName] || {};

                    let html = `<div style="font-family:'Patrick Hand';font-size:16px;font-weight:bold;margin-bottom:8px;color:#d97757">${catName}</div>`;

                    // 目标
                    if (info.targetValue > 0) {
                        const total = (Number(info.todayValue) || 0) + (Number(info.thisMealValue) || 0);
                        const pct = info.targetValue > 0 ? Math.round((total / info.targetValue) * 100) : 0;

                        // 脂肪、钠：显示“还剩余/已超出”；其余：显示“已摄入”
                        const isRemainWording = (catName === '脂肪' || catName === '钠');
                        let pctText = '';
                        if (isRemainWording) {
                            if (pct >= 100) {
                                pctText = `已超出 ${pct - 100}%`;
                            } else {
                                pctText = `还剩余 ${100 - pct}%`;
                            }
                        } else {
                            pctText = `已摄入 ${pct}%`;
                        }

                        const defaultLabel = info.isDefault ? ' <span style="font-size:10px;color:#aaa">(NRV参考值)</span>' : '';
                        html += `<div style="margin-bottom:6px;font-size:12px;color:#8c7f70">目标：${info.targetValue} ${info.unit}${defaultLabel}（${pctText}）</div>`;
                    }

                    // 本次
                    html += `<div style="display:flex;justify-content:space-between;min-width:160px;margin:3px 0;">
                        <span style="color:${this.colors.thisMeal}">● 本次</span>
                        <span>${info.thisMealValue} ${info.unit}</span>
                    </div>`;

                    // 今日累计
                    html += `<div style="display:flex;justify-content:space-between;min-width:160px;margin:3px 0;">
                        <span style="color:${this.colors.todayIntake}">● 今日累计</span>
                        <span>${info.todayValue} ${info.unit}</span>
                    </div>`;

                    return html;
                }
            },
            legend: {
                show: true,
                bottom: 0,
                itemGap: 20,
                textStyle: { color: '#8c7f70', fontFamily: 'Lora' }
            },
            grid: {
                left: 160, // 左侧留足空间，避免标签被压缩/省略
                right: 30,
                top: 10,
                bottom: 40,
                containLabel: false
            },
            xAxis: {
                type: 'value',
                max: axisMax, // 动态：对 >100% 友好
                splitLine: { lineStyle: { color: 'rgba(92, 85, 78, 0.1)' } }, // Faint pencil line
                axisLabel: { color: '#b0a69a', formatter: '{value}%', fontFamily: 'Lora' }
            },
            yAxis: {
                type: 'category',
                data: categories,
                axisLabel: {
                    margin: 10,
                    interval: 0, // 强制显示全部 6 条标签
                    formatter: (value) => {
                        const info = data.details[value];
                        if (!info) return value;
                        const current = Math.round(info.todayValue + info.thisMealValue);
                        const target = info.targetValue > 0 ? info.targetValue : '-';
                        return `{title|${value}}  {val|${current}/${target}${info.unit}}`;
                    },
                    rich: {
                        title: {
                            color: '#4a3e35', // Dark Ink
                            fontWeight: 500,
                            fontFamily: 'Patrick Hand',
                            fontSize: 14,
                            lineHeight: 18
                        },
                        val: {
                            color: '#8c7f70', // Faded Ink
                            fontSize: 11,
                            fontFamily: 'Lora',
                            lineHeight: 14
                        }
                    }
                },
                axisLine: { show: false },
                axisTick: { show: false }
            },
            series: [
                {
                    name: '今日已摄入',
                    type: 'bar',
                    stack: 'total',
                    barWidth: 14,
                    itemStyle: { color: this.colors.todayIntake, borderRadius: [6, 0, 0, 6] },
                    data: todayData
                },
                {
                    name: '本次分析',
                    type: 'bar',
                    stack: 'total',
                    barWidth: 14,
                    itemStyle: { color: this.colors.thisMeal, borderRadius: [0, 6, 6, 0] },
                    data: thisMealData
                },
                {
                    type: 'line',
                    markLine: {
                        silent: true,
                        symbol: 'none',
                        lineStyle: { color: 'rgba(92, 85, 78, 0.2)', type: 'dashed' },
                        data: [{ xAxis: 100 }],
                        label: { show: false }
                    }
                }
            ]
        };
    },


    /**
     * 构建百分比数据
     */
    buildPercentageData(currentTotals, energyUnit) {
        const today = this.todaySummary || {};
        const target = this.userTarget || {};
        const profile = Dashboard.profile?.diet || {};

        const getTarget = (k1, k2) => target[k1] || profile[k2] || 0;

        // 定义数据源，注意这里的顺序！与 buildOption 中的翻转逻辑对应
        // 如果 target 为 0/null，使用通用参考值做分母，避免除以零或进度条消失
        const nutrients = [
            {
                key: '能量',
                this: (currentTotals.totalEnergy || 0),
                today: (today.consumed_energy_kj || 0) / 4.184, // stored as kj, convert to kcal for ratio
                target: (getTarget('daily_energy_kj_target', 'daily_energy_kj_target') || 0) / 4.184,
                defaultTarget: 2000,
                unit: 'kcal'
            },
            {
                key: '蛋白质',
                this: currentTotals.totalProtein || 0,
                today: today.consumed_protein_g || 0,
                target: getTarget('protein_g_target', 'protein_g_target'),
                defaultTarget: 60,
                unit: 'g'
            },
            {
                key: '脂肪',
                this: currentTotals.totalFat || 0,
                today: today.consumed_fat_g || 0,
                target: getTarget('fat_g_target', 'fat_g_target'),
                defaultTarget: 60,
                unit: 'g'
            },
            {
                key: '碳水',
                this: currentTotals.totalCarb || 0,
                today: today.consumed_carbs_g || 0,
                target: getTarget('carbs_g_target', 'carbs_g_target'),
                defaultTarget: 300,
                unit: 'g'
            },
            {
                key: '纤维',
                this: currentTotals.totalFiber || 0,
                today: today.consumed_fiber_g || 0,
                target: getTarget('fiber_g_target', 'fiber_g_target'),
                defaultTarget: 25,
                unit: 'g'
            },
            {
                key: '钠',
                this: currentTotals.totalSodiumMg || 0,
                today: today.consumed_sodium_mg || 0,
                target: getTarget('sodium_mg_target', 'sodium_mg_target'),
                defaultTarget: 2000,
                unit: 'mg'
            }
        ];

        const thisMealPercent = [];
        const todayPercent = [];
        const details = {};

        nutrients.forEach(n => {
            let t = n.target;
            let isDefault = false;

            // 如果没有用户目标，使用默认参考值作为分母
            if (!t || t <= 0) {
                t = n.defaultTarget;
                isDefault = true;
            }

            // 确保显示数值使用了正确的单位转换 (如果是 kJ 模式)
            const displayFactor = (n.key === '能量' && energyUnit === 'kJ') ? 4.184 : 1;
            const displayUnit = (n.key === '能量') ? energyUnit : n.unit;

            thisMealPercent.push(t > 0 ? (n.this / t) * 100 : 0);
            todayPercent.push(t > 0 ? (n.today / t) * 100 : 0);

            details[n.key] = {
                thisMealValue: Math.round(n.this * displayFactor * 10) / 10,
                todayValue: Math.round(n.today * displayFactor * 10) / 10,
                targetValue: Math.round(t * displayFactor * 10) / 10,
                unit: displayUnit,
                isDefault: isDefault // 标记是否使用了默认值
            };
        });

        return { thisMealPercent, todayPercent, details };
    },

    dispose() {
        if (this.chartInstance) {
            this.chartInstance.dispose();
            this.chartInstance = null;
        }
    }
};

window.NutritionChartModule = NutritionChartModule;
