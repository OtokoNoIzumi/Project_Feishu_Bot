/**
 * 结果解析模块
 * 
 * 负责将后端返回的原始 JSON 数据转换为前端统一的数据结构
 * 处理 Schema 兼容性、计算初始总能量等
 */
const ParserModule = {
    parseResult(rawResult, mode) {
        if (mode === 'diet') {
            return this.parseDietResult(rawResult);
        } else {
            return this.parseKeepResult(rawResult);
        }
    },

    parseDietResult(data) {
        const summary = data.meal_summary || {};

        // 使用 KJ 进行高精度累加，确保持续一致性
        let totalEnergyKJ = 0;
        let totalProtein = 0;
        let totalFat = 0;
        let totalCarb = 0;
        let totalSodiumMg = 0;
        let totalFiberG = 0;

        const dishes = [];

        (data.dishes || []).forEach((dish, i) => {
            let dishWeight = 0;

            // 临时累加器
            let dishEnergyKJ = 0;
            let dishProtein = 0;
            let dishFat = 0;
            let dishCarb = 0;
            let dishSodiumMg = 0;
            let dishFiberG = 0;

            (dish.ingredients || []).forEach(ing => {
                const weight = Number(ing.weight_g) || 0;
                dishWeight += weight;

                // 累加宏量
                if (ing.macros) {
                    dishProtein += Number(ing.macros.protein_g) || 0;
                    dishFat += Number(ing.macros.fat_g) || 0;
                    dishCarb += Number(ing.macros.carbs_g) || 0;
                    dishSodiumMg += Number(ing.macros.sodium_mg) || 0;
                    dishFiberG += Number(ing.macros.fiber_g) || 0;
                }

                // 计算能量 (统一转为 KJ 累加)
                // 优先使用后端返回的 energy_kj (Label OCR 或 高精度计算值)
                let itemEnergyKJ = 0;
                const backendKJ = Number(ing.energy_kj);

                if (!isNaN(backendKJ) && backendKJ > 0) {
                    itemEnergyKJ = backendKJ;
                } else if (ing.macros) {
                    // Fallback: 使用 EnergyUtils 计算 (Kcal -> KJ)
                    const kcal = EnergyUtils.macrosToKcal(
                        ing.macros.protein_g,
                        ing.macros.fat_g,
                        ing.macros.carbs_g
                    );
                    itemEnergyKJ = EnergyUtils.kcalToKJ(kcal);
                }

                dishEnergyKJ += itemEnergyKJ;
            });

            dishes.push({
                id: i,
                name: dish.standard_name || '未知',
                weight: Math.round(dishWeight),
                enabled: true,
                source: 'ai',
                ingredients: (dish.ingredients || []).map(ing => {
                    const weightG = Number(ing.weight_g) || 0;
                    const proteinG = Number(ing.macros?.protein_g) || 0;
                    const fatG = Number(ing.macros?.fat_g) || 0;
                    const carbsG = Number(ing.macros?.carbs_g) || 0;
                    const sodiumMg = Number(ing.macros?.sodium_mg) || 0;
                    const fiberG = Number(ing.macros?.fiber_g) || 0;

                    const density = weightG > 0 ? {
                        protein_per_g: proteinG / weightG,
                        fat_per_g: fatG / weightG,
                        carbs_per_g: carbsG / weightG,
                        sodium_per_g: sodiumMg / weightG,
                        fiber_per_g: fiberG / weightG,
                    } : null;

                    return {
                        name_zh: ing.name_zh,
                        weight_g: weightG,
                        weight_method: ing.weight_method,
                        data_source: ing.data_source,
                        energy_kj: Number(ing.energy_kj) || 0, // 保持原始精度
                        macros: {
                            protein_g: proteinG,
                            fat_g: fatG,
                            carbs_g: carbsG,
                            sodium_mg: sodiumMg,
                            fiber_g: fiberG,
                        },
                        _density: density,
                        _proportionalScale: false,
                    };
                }),
            });

            totalEnergyKJ += dishEnergyKJ;
            totalProtein += dishProtein;
            totalFat += dishFat;
            totalCarb += dishCarb;
            totalSodiumMg += dishSodiumMg;
            totalFiberG += dishFiberG;
        });

        // 转换回 Kcal 以通过 parse 接口 (如果前端主要消费 Kcal)
        // 但这里我们保留高精度，交由前端展示层决定小数位数
        const totalEnergyKcal = EnergyUtils.kJToKcal(totalEnergyKJ);

        return {
            type: 'diet',
            summary: {
                mealName: summary.meal_name || '饮食记录',
                userMealName: summary.user_meal_name || null,
                dietTime: summary.diet_time || '',
                // 返回计算出的总 Kcal (保留一定精度，避免过早取整)
                // 前端如果需要 KJ，应该使用 EnergyUtils.kcalToKJ(totalEnergy) 或直接显示
                // 为了兼容旧逻辑 (return Number)，这里不取整
                totalEnergy: totalEnergyKcal,
                // 同时也附带 KJ 值供需要时使用
                totalEnergyKJ: totalEnergyKJ,

                totalProtein: Math.round(totalProtein * 10) / 10,
                totalFat: Math.round(totalFat * 10) / 10,
                totalCarb: Math.round(totalCarb * 10) / 10,
                totalFiber: Math.round(totalFiberG * 10) / 10,
                totalSodiumMg: Math.round(totalSodiumMg),
            },
            dishes: dishes,
            advice: summary.advice || '',
            extraImageSummary: data.extra_image_summary || '',
            userNoteProcess: data.user_note_process || '',
            // 识别到的营养标签
            capturedLabels: (data.captured_labels || data.labels_snapshot || []).map(lb => ({
                productName: lb.product_name || '',
                brand: lb.brand || '',
                variant: lb.variant || '',
                tableUnit: lb.table_unit || 'g',
                tableAmount: Number(lb.table_amount) || 100,
                densityFactor: lb.density_factor || lb.density || 1.0,
                energyKjPerServing: lb.energy_kj_per_serving || 0,
                proteinGPerServing: lb.protein_g_per_serving || 0,
                fatGPerServing: lb.fat_g_per_serving || 0,
                carbsGPerServing: lb.carbs_g_per_serving || 0,
                sodiumMgPerServing: lb.sodium_mg_per_serving || 0,
                fiberGPerServing: lb.fiber_g_per_serving || 0,
                customNote: lb.custom_note || '',
            })),
            // AI 识别的发生时间
            occurredAt: data.occurred_at || null,
            // 上下文数据
            context: data.context || null,
        };
    },

    parseKeepResult(data) {
        // Keep 返回的是 scale_events, sleep_events, body_measure_events
        const result = {
            type: 'keep',
            scaleEvents: data.scale_events || [],
            sleepEvents: data.sleep_events || [],
            bodyMeasureEvents: data.body_measure_events || [],
        };

        return result;
    },
};

window.ParserModule = ParserModule;
