/**
 * Diet 编辑模块
 *
 * 处理菜品增删改、成分编辑、汇总计算
 * 这些函数会挂载到 Dashboard 上下文执行，this 指向 Dashboard 实例
 */

const DietEditModule = {
    // 切换营养标签区域的折叠状态
    toggleLabelsSection() {
        const content = document.getElementById('labels-content');
        const icon = document.getElementById('labels-toggle-icon');
        if (content && icon) {
            const isCollapsed = content.classList.contains('collapsed');
            content.classList.toggle('collapsed');
            icon.textContent = isCollapsed ? '▲' : '▼';
        }
    },

    // 更新营养标签字段
    updateLabel(index, field, value) {
        if (this.currentLabels && this.currentLabels[index]) {
            this.currentLabels[index][field] = value;
            this.markModified();
        }
    },

    updateDish(index, field, value) {
        if (this.currentDishes && this.currentDishes[index]) {
            // AI 菜式：菜式层级不可编辑（只允许编辑 ingredients）
            if (this.currentDishes[index].source === 'ai') {
                return;
            }
            this.currentDishes[index][field] = field === 'name' ? value : (parseFloat(value) || 0);
            this.recalculateDietSummary(true);

            // 优化：仅更新当前行 DOM，不重绘整个列表以保持焦点
            this.updateDishRowDOM(index);
        }
    },

    updateIngredient(dishIndex, ingIndex, field, value) {
        const dish = this.currentDishes?.[dishIndex];
        if (!dish || dish.source !== 'ai') return;
        const ing = dish.ingredients?.[ingIndex];
        if (!ing) return;

        if (field === 'weight_g') {
            const newWeight = parseFloat(value) || 0;
            // 如果开启了等比缩放且有密度数据，按比例调整所有营养素
            if (ing._proportionalScale && ing._density && newWeight > 0) {
                ing.macros.protein_g = Math.round(ing._density.protein_per_g * newWeight * 100) / 100;
                ing.macros.fat_g = Math.round(ing._density.fat_per_g * newWeight * 100) / 100;
                ing.macros.carbs_g = Math.round(ing._density.carbs_per_g * newWeight * 100) / 100;
                ing.macros.sodium_mg = Math.round(ing._density.sodium_per_g * newWeight * 100) / 100;
                ing.macros.fiber_g = Math.round(ing._density.fiber_per_g * newWeight * 100) / 100;
            }
            ing.weight_g = newWeight;
        } else {
            ing.macros = ing.macros || {};
            ing.macros[field] = parseFloat(value) || 0;

            // 如果修改了营养素，更新密度缓存（以便后续等比缩放使用新比例）
            // 注意：这里逻辑上稍微有点问题，如果用户正在修改营养素，是否应该立即更新密度？
            // 简单处理：每次修改都更新 density，保证下次切回改重量时比例是最新的
            if (ing.weight_g > 0) {
                ing._density = ing._density || {};
                const fieldToDensity = {
                    'protein_g': 'protein_per_g',
                    'fat_g': 'fat_per_g',
                    'carbs_g': 'carbs_per_g',
                    'sodium_mg': 'sodium_per_g',
                    'fiber_g': 'fiber_per_g',
                };
                if (fieldToDensity[field]) {
                    ing._density[fieldToDensity[field]] = ing.macros[field] / ing.weight_g;
                }
            }
        }

        this.recalculateDietSummary(true);
        // 优化：仅更新相关 DOM
        this.updateDishDOM(dishIndex, ingIndex, field);
    },

    // 局部更新：AI 菜式块（更新 Header 统计 + 联动更新 Ingredient 行）
    updateDishDOM(dishIndex, ingIndex, changedField) {
        const dish = this.currentDishes?.[dishIndex];
        if (!dish) return;

        // 1. 找到 Dish Block
        const dishBlock = document.querySelector(`.diet-dish-block[data-dish-index="${dishIndex}"]`);
        if (!dishBlock) return;

        // 2. 更新 Header 统计数据
        const totals = this.getDishTotals(dish);
        const unit = this.getEnergyUnit();

        let energyText;
        // 优先使用聚合的高精度 energy_kj
        if (totals.energy_kj) {
            if (unit === 'kcal') {
                energyText = Math.round(EnergyUtils.kJToKcal(totals.energy_kj));
            } else {
                // KJ 保留 1 位小数
                energyText = (Math.round(totals.energy_kj * 10) / 10).toFixed(1);
            }
        } else {
            energyText = this.formatEnergyFromMacros(totals.protein, totals.fat, totals.carb);
        }

        const setStat = (type, val) => {
            const el = dishBlock.querySelector(`.diet-stat[data-stat-type="${type}"] .v`);
            if (el) el.textContent = val;
        };
        const r1 = (x) => Math.round((Number(x) || 0) * 10) / 10;
        const r0 = (x) => Math.round(Number(x) || 0);

        setStat('energy', `${energyText} ${unit}`);
        setStat('protein', `${r1(totals.protein)}g`);
        setStat('fat', `${r1(totals.fat)}g`);
        setStat('carb', `${r1(totals.carb)}g`);
        setStat('fiber', `${r1(totals.fiber)}g`);
        setStat('sodium', `${r0(totals.sodium_mg)}mg`);
        setStat('weight', `${r1(totals.weight)}g`);

        // 3. 如果触发了联动（修改重量且开启了比例），需要更新该行所有 input
        const ing = dish.ingredients?.[ingIndex];
        if (ing && changedField === 'weight_g' && ing._proportionalScale) {
            const row = dishBlock.querySelector(`tr[data-ing-index="${ingIndex}"]`);
            if (row) {
                // 定义映射
                const map = {
                    'protein_g': ing.macros.protein_g,
                    'fat_g': ing.macros.fat_g,
                    'carbs_g': ing.macros.carbs_g,
                    'fiber_g': ing.macros.fiber_g,
                    'sodium_mg': ing.macros.sodium_mg,
                };
                // 遍历并更新
                Object.keys(map).forEach(key => {
                    const input = row.querySelector(`input[data-field="${key}"]`);
                    if (input && input !== document.activeElement) {
                        input.value = map[key];
                    }
                });

                // 同时也更新该行的能量显示 (read-only)
                const energyInput = row.querySelector('.js-energy-display');
                if (energyInput) {
                    energyInput.value = this.formatEnergyFromMacros(ing.macros.protein_g, ing.macros.fat_g, ing.macros.carbs_g);
                }
            }
        } else if (ing) {
            // 普通 update，也许需要更新行内的能量显示 (当修改 P/F/C 时)
            const row = dishBlock.querySelector(`tr[data-ing-index="${ingIndex}"]`);
            if (row) {
                const energyInput = row.querySelector('.js-energy-display');
                if (energyInput) {
                    energyInput.value = this.formatEnergyFromMacros(ing.macros?.protein_g, ing.macros?.fat_g, ing.macros?.carbs_g);
                }
            }
        }
    },

    // 局部更新：用户菜式行
    updateDishRowDOM(index) {
        const dish = this.currentDishes?.[index];
        if (!dish) return;

        // 找到行 (可能是 Desktop Table 或 Mobile List，这里主要针对 Desktop Table 优化，因为 Mobile 一般不显示 huge table)
        // 注意：Mobile 端结构不同，这里暂时只处理 Desktop Table 的 data-dish-index
        const row = document.querySelector(`tr[data-dish-index="${index}"]`);
        if (!row) return;

        // 更新能量 (read-only)
        const energyText = this.formatEnergyFromMacros(dish.protein, dish.fat, dish.carb);
        const energyInput = row.querySelector('.js-energy-display');
        if (energyInput) {
            energyInput.value = energyText;
        }
    },

    // 委托给 EnergyUtils (为了方便内部调用)
    formatEnergyFromMacros(p, f, c) {
        return EnergyUtils.formatEnergyFromMacros(p, f, c, this.getEnergyUnit());
    },

    // 获取当前能量单位 - 【重构】统一使用 ProfileModule 作为唯一数据源
    getEnergyUnit() {
        const p = typeof ProfileModule !== 'undefined' ? ProfileModule.getCurrentProfile() : null;
        return (p?.diet?.energy_unit) || 'kJ';
    },

    toggleIngredients(dishId) {
        const curr = this.dietIngredientsCollapsed?.[dishId];
        // 默认折叠：undefined 视为 true
        const next = curr === false ? true : false;
        this.dietIngredientsCollapsed[dishId] = next;
        this.renderDietDishes();
    },

    // 切换成分的等比缩放开关
    toggleProportionalScale(dishIndex, ingIndex) {
        const dish = this.currentDishes?.[dishIndex];
        if (!dish || dish.source !== 'ai') return;
        const ing = dish.ingredients?.[ingIndex];
        if (!ing) return;

        // 切换状态
        ing._proportionalScale = !ing._proportionalScale;

        // 如果开启，则初始化密度
        if (ing._proportionalScale && !ing._density && ing.weight_g > 0) {
            ing._density = {
                protein_per_g: (ing.macros?.protein_g || 0) / ing.weight_g,
                fat_per_g: (ing.macros?.fat_g || 0) / ing.weight_g,
                carbs_per_g: (ing.macros?.carbs_g || 0) / ing.weight_g,
                sodium_per_g: (ing.macros?.sodium_mg || 0) / ing.weight_g,
                fiber_per_g: (ing.macros?.fiber_g || 0) / ing.weight_g,
            };
        }

        this.renderDietDishes();
    },

    addDish() {
        if (!this.currentDishes) this.currentDishes = [];
        this.currentDishes.push({
            name: '新菜品',
            weight: 100,
            protein: 0,
            fat: 0,
            carb: 0,
            fiber: 0,
            sodium_mg: 0,
            source: 'user', // 标记为用户手动添加
            enabled: true
        });
        this.renderDietDishes();
        this.recalculateDietSummary(true);
        // 滚动到底部
        setTimeout(() => {
            const container = document.getElementById('diet-dishes-container');
            if (container) container.scrollTop = container.scrollHeight;
        }, 100);
    },

    removeDish(index) {
        if (this.currentDishes) {
            const d = this.currentDishes[index];
            if (d && d.source !== 'user') {
                this.addMessage('AI 识别的菜式不支持删除，可取消勾选以停用', 'assistant');
                return;
            }
            this.currentDishes.splice(index, 1);
            this.renderDietDishes();
            this.recalculateDietSummary(true);
        }
    },

    // 重新计算总览数据
    recalculateDietSummary(markModified = true) {
        if (!this.currentDishes) return;

        const dishes = this.currentDishes.filter(d => d.enabled !== false);
        const totals = {
            totalEnergyKJ: 0, // 新增：高精度总能量 (KJ)
            totalProtein: 0,
            totalFat: 0,
            totalCarb: 0,
            totalFiber: 0,
            totalSodiumMg: 0,
            totalWeightG: 0,
        };

        dishes.forEach(d => {
            const dt = this.getDishTotals(d);
            totals.totalProtein += dt.protein;
            totals.totalFat += dt.fat;
            totals.totalCarb += dt.carb;
            totals.totalFiber += dt.fiber;
            totals.totalSodiumMg += dt.sodium_mg;
            totals.totalWeightG += dt.weight;

            // 优先累加高精度 KJ
            totals.totalEnergyKJ += dt.energy_kj;
        });

        // 舍入 (宏量保留 1 位小数)
        totals.totalProtein = Math.round(totals.totalProtein * 10) / 10;
        totals.totalFat = Math.round(totals.totalFat * 10) / 10;
        totals.totalCarb = Math.round(totals.totalCarb * 10) / 10;
        totals.totalFiber = Math.round(totals.totalFiber * 10) / 10;
        totals.totalSodiumMg = Math.round(totals.totalSodiumMg);
        totals.totalWeightG = Math.round(totals.totalWeightG);

        // 为了兼容旧逻辑，totalEnergy (Kcal) 也保留，但基于 KJ 计算且不取整
        totals.totalEnergy = EnergyUtils.kJToKcal(totals.totalEnergyKJ);

        this.currentDietTotals = totals;

        // 更新 DOM
        const setText = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.textContent = v;
        };

        const unit = this.getEnergyUnit();
        let displayTotalEnergy;

        if (unit === 'kcal') {
            displayTotalEnergy = Math.round(totals.totalEnergy); // Kcal 显示整数
        } else {
            // KJ 显示整数 (用户要求)
            displayTotalEnergy = Math.round(totals.totalEnergyKJ);
        }

        setText('sum-total-energy', displayTotalEnergy);
        setText('sum-energy-unit', unit);
        setText('sum-total-protein', this.currentDietTotals.totalProtein);
        setText('sum-total-fat', this.currentDietTotals.totalFat);
        setText('sum-total-carb', this.currentDietTotals.totalCarb);
        setText('sum-total-fiber', this.currentDietTotals.totalFiber);
        setText('sum-total-sodium', this.currentDietTotals.totalSodiumMg);
        setText('sum-total-weight', this.currentDietTotals.totalWeightG);

        const subtitle = document.getElementById('diet-subtitle');
        if (subtitle && this.currentDietMeta) {
            subtitle.textContent = `${dishes.length} 种食物 · ${this.currentDietMeta.dietTime || ''}`;
        }

        // 同步更新营养图表
        if (typeof NutritionChartModule !== 'undefined' && NutritionChartModule.chartInstance) {
            try {
                NutritionChartModule.updateCurrentMeal(totals, this.getEnergyUnit());
            } catch (e) {
                console.warn('[DietEdit] Chart update skipped (view likely hidden)');
            }
        }

        if (markModified) this.markModified();
    },

    markModified() {
        if (this.currentSession) {
            this.currentSession.isSaved = false;
        }
        this.updateStatus('modified');
        this.updateButtonStates(this.currentSession);
    },

    collectEditedData() {
        // 目前只对 diet 结果做“确认面板编辑”
        if (this.mode !== 'diet') return {};

        if (!this.currentDietTotals) {
            this.recalculateDietSummary(false);
        }

        const totals = this.currentDietTotals || {};
        const mealName = this.currentDietMeta?.mealName || '饮食记录';
        const dietTime = this.currentDietMeta?.dietTime || '';
        const ExtraImageSummary = this.currentSession?.versions[this.currentSession.currentVersion - 1]?.parsedData?.extraImageSummary || '';

        // 1. 获取原始 Raw Result 以保留 Metadata (status, saved_record_id等)
        const saved = this.currentSession.isSaved;
        // console.log('currentSession', this.currentSession);
        // console.log('currentDietMeta', this.currentDietMeta);

        const editedDishes = (this.currentDishes || []).filter(d => d.enabled !== false).map(d => {
            // A. AI 识别菜式
            if (d.source === 'ai' && Array.isArray(d.ingredients) && d.ingredients.length > 0) {
                return {
                    standard_name: d.name,
                    ingredients: (d.ingredients || []).map(ing => ({
                        name_zh: ing.name_zh,
                        weight_g: Number(ing.weight_g) || 0,
                        weight_method: ing.weight_method,
                        data_source: ing.data_source,
                        energy_kj: Number(ing.energy_kj) || 0, // 保留原始 KJ
                        macros: {
                            protein_g: Number(ing.macros?.protein_g) || 0,
                            fat_g: Number(ing.macros?.fat_g) || 0,
                            carbs_g: Number(ing.macros?.carbs_g) || 0,
                            fiber_g: Number(ing.macros?.fiber_g) || 0,
                            sodium_mg: Number(ing.macros?.sodium_mg) || 0,
                        },
                    })),
                };
            }

            // B. 用户新增菜式
            return {
                standard_name: d.name,
                ingredients: [
                    {
                        name_zh: d.name,
                        weight_g: Number(d.weight) || 0,
                        weight_method: "user_edit",
                        data_source: "user_edit",
                        // 用户菜式没有 energy_kj，需计算
                        energy_kj: Math.round(EnergyUtils.kcalToKJ(EnergyUtils.macrosToKcal(d.protein, d.fat, d.carb)) * 10) / 10,
                        macros: {
                            protein_g: Number(d.protein) || 0,
                            fat_g: Number(d.fat) || 0,
                            carbs_g: Number(d.carb) || 0,
                            fiber_g: Number(d.fiber) || 0,
                            sodium_mg: Number(d.sodium_mg) || 0,
                        },
                    }
                ],
            };
        });

        // 收集编辑后的营养标签
        const editedLabels = (this.currentLabels || []).map(lb => ({
            product_name: lb.productName || '',
            brand: lb.brand || '',
            variant: lb.variant || '',
            serving_size: lb.servingSize || '100g',
            energy_kj_per_serving: lb.energyKjPerServing || 0,
            protein_g_per_serving: lb.proteinGPerServing || 0,
            fat_g_per_serving: lb.fatGPerServing || 0,
            carbs_g_per_serving: lb.carbsGPerServing || 0,
            sodium_mg_per_serving: lb.sodiumMgPerServing || 0,
            fiber_g_per_serving: lb.fiberGPerServing || 0,
            custom_note: lb.customNote || '',
        }));

        // 2. 构造并合并返回对象
        // 优先级：编辑后的数据 > 原始数据
        return {
            isSaved: saved,
            meal_summary: {
                meal_name: mealName,
                diet_time: dietTime,
                // 这里按标准输出：保留一位小数的 KJ
                total_energy_kj: Math.round(totals.totalEnergyKJ * 10) / 10,
                total_protein_g: Number(totals.totalProtein) || 0,
                total_fat_g: Number(totals.totalFat) || 0,
                total_carbs_g: Number(totals.totalCarb) || 0,
                total_fiber_g: Number(totals.totalFiber) || 0,
                total_sodium_mg: Number(totals.totalSodiumMg) || 0,
            },
            dishes: editedDishes,
            captured_labels: editedLabels,
            extra_image_summary: ExtraImageSummary,
            occurred_at: this.currentDietMeta?.occurredAt || null,
        };
    },

    getDishTotals(dish) {
        // AI：按 ingredients 加总
        if (dish?.source === 'ai') {
            const ings = dish.ingredients || [];
            let totalKJ = 0;
            let totalW = 0;
            let totalP = 0;
            let totalF = 0;
            let totalC = 0;
            let totalFib = 0;
            let totalNa = 0;

            ings.forEach(ing => {
                totalW += Number(ing.weight_g) || 0;
                totalP += Number(ing.macros?.protein_g) || 0;
                totalF += Number(ing.macros?.fat_g) || 0;
                totalC += Number(ing.macros?.carbs_g) || 0;
                totalFib += Number(ing.macros?.fiber_g) || 0;
                totalNa += Number(ing.macros?.sodium_mg) || 0;

                // 核心：优先使用 energy_kj
                let e = Number(ing.energy_kj);
                if (!isNaN(e) && e > 0) {
                    totalKJ += e;
                } else {
                    // Fallback using EnergyUtils logic (via macros)
                    const kcal = EnergyUtils.macrosToKcal(
                        ing.macros?.protein_g,
                        ing.macros?.fat_g,
                        ing.macros?.carbs_g
                    );
                    totalKJ += EnergyUtils.kcalToKJ(kcal);
                }
            });

            return {
                weight: totalW,
                protein: totalP,
                fat: totalF,
                carb: totalC,
                fiber: totalFib,
                sodium_mg: totalNa,
                energy_kj: totalKJ,
            };
        }

        // User created dish (manual input)
        const p = Number(dish?.protein) || 0;
        const f = Number(dish?.fat) || 0;
        const c = Number(dish?.carb) || 0;
        // Calc energy for user dish always from macros (standard rule)
        const e_struct_kj = EnergyUtils.kcalToKJ(EnergyUtils.macrosToKcal(p, f, c));

        return {
            weight: Number(dish?.weight) || 0,
            protein: p,
            fat: f,
            carb: c,
            fiber: Number(dish?.fiber) || 0,
            sodium_mg: Number(dish?.sodium_mg) || 0,
            energy_kj: e_struct_kj,
        };
    },

    toggleDishEnabled(index, enabled) {
        if (this.currentDishes && this.currentDishes[index]) {
            this.currentDishes[index].enabled = Boolean(enabled);
            this.recalculateDietSummary(true);
            this.renderDietDishes();
        }
    },
};

// 挂载到全局
window.DietEditModule = DietEditModule;
