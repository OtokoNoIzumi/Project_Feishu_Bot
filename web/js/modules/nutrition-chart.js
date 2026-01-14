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

    // 颜色定义
    colors: {
        // 更克制、对比更舒服（深色背景）
        thisMeal: '#a78bfa',     // Purple-400
        todayIntake: '#5eead4',  // Teal-300
        target: '#fb7185',       // Rose-400（保留备用）
        background: 'rgba(148, 163, 184, 0.06)',
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
                backgroundColor: 'rgba(20, 20, 35, 0.95)',
                borderColor: 'rgba(99, 102, 241, 0.3)',
                padding: [12, 16],
                textStyle: { color: '#e2e8f0', fontSize: 13 },
                formatter: (params) => {
                    // params[0] 是第一个系列的数据
                    const index = params[0].dataIndex;
                    // 因为数据翻转了，所以要用 categories[index] 获取正确的名称
                    const catName = categories[index];
                    const info = data.details[catName] || {};

                    let html = `<div style="font-weight:bold;margin-bottom:8px;color:#fff">${catName}</div>`;

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

                        html += `<div style="margin-bottom:6px;font-size:12px;color:#94a3b8">目标：${info.targetValue} ${info.unit}（${pctText}）</div>`;
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
                textStyle: { color: '#94a3b8' }
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
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
                axisLabel: { color: '#64748b', formatter: '{value}%' }
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
                            color: '#e2e8f0',
                            fontWeight: 600,
                            lineHeight: 18
                        },
                        val: {
                            color: '#94a3b8',
                            fontSize: 11,
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
                        lineStyle: { color: 'rgba(255,255,255,0.15)', type: 'dashed' },
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
        const nutrients = [
            {
                key: '能量',
                this: (currentTotals.totalEnergy || 0),
                today: (today.consumed_energy_kj || 0) / 4.184, // stored as kj, convert to kcal for ratio
                target: (getTarget('daily_energy_kj_target', 'daily_energy_kj_target') || 0) / 4.184,
                unit: 'kcal'
            },
            {
                key: '蛋白质',
                this: currentTotals.totalProtein || 0,
                today: today.consumed_protein_g || 0,
                target: getTarget('protein_g_target', 'protein_g_target'),
                unit: 'g'
            },
            {
                key: '脂肪',
                this: currentTotals.totalFat || 0,
                today: today.consumed_fat_g || 0,
                target: getTarget('fat_g_target', 'fat_g_target'),
                unit: 'g'
            },
            {
                key: '碳水',
                this: currentTotals.totalCarb || 0,
                today: today.consumed_carbs_g || 0,
                target: getTarget('carbs_g_target', 'carbs_g_target'),
                unit: 'g'
            },
            {
                key: '纤维',
                this: currentTotals.totalFiber || 0,
                today: today.consumed_fiber_g || 0,
                target: getTarget('fiber_g_target', 'fiber_g_target') || 25,
                unit: 'g'
            },
            {
                key: '钠',
                this: currentTotals.totalSodiumMg || 0,
                today: today.consumed_sodium_mg || 0,
                target: getTarget('sodium_mg_target', 'sodium_mg_target') || 2000,
                unit: 'mg'
            }
        ];

        const thisMealPercent = [];
        const todayPercent = [];
        const details = {};

        nutrients.forEach(n => {
            const t = n.target || 1;
            // 确保显示数值使用了正确的单位转换 (如果是 kJ 模式)
            const displayFactor = (n.key === '能量' && energyUnit === 'kJ') ? 4.184 : 1;
            const displayUnit = (n.key === '能量') ? energyUnit : n.unit;

            thisMealPercent.push(n.target > 0 ? (n.this / t) * 100 : 0);
            todayPercent.push(n.target > 0 ? (n.today / t) * 100 : 0);

            details[n.key] = {
                thisMealValue: Math.round(n.this * displayFactor * 10) / 10,
                todayValue: Math.round(n.today * displayFactor * 10) / 10,
                targetValue: Math.round(n.target * displayFactor * 10) / 10,
                unit: displayUnit
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
