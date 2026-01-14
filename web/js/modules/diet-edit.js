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
            // 重新渲染以更新能量显示
            this.renderDietDishes();
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
        this.renderDietDishes();
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
            totalEnergy: 0,
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
            // 能量重新计算 (kcal)
            totals.totalEnergy += this.macrosToKcal(dt.protein, dt.fat, dt.carb);
        });

        // 舍入
        totals.totalEnergy = Math.round(totals.totalEnergy);
        totals.totalProtein = Math.round(totals.totalProtein * 10) / 10;
        totals.totalFat = Math.round(totals.totalFat * 10) / 10;
        totals.totalCarb = Math.round(totals.totalCarb * 10) / 10;
        totals.totalFiber = Math.round(totals.totalFiber * 10) / 10;
        totals.totalSodiumMg = Math.round(totals.totalSodiumMg);
        totals.totalWeightG = Math.round(totals.totalWeightG);

        this.currentDietTotals = totals;

        // 更新 DOM
        const setText = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.textContent = v;
        };

        setText('sum-total-energy', this.currentDietTotals.totalEnergy);
        setText('sum-energy-unit', this.getEnergyUnit());
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
        const unit = this.getEnergyUnit();
        const totalEnergyKcal = unit === 'kcal'
            ? (Number(totals.totalEnergy) || 0)
            : this.kJToKcal(Number(totals.totalEnergy) || 0);

        const editedDishes = (this.currentDishes || []).filter(d => d.enabled !== false).map(d => {
            // A. AI 识别菜式：保留 ingredients 结构，直接保存“逐成分编辑后的数据”
            if (d.source === 'ai' && Array.isArray(d.ingredients) && d.ingredients.length > 0) {
                return {
                    standard_name: d.name,
                    ingredients: (d.ingredients || []).map(ing => ({
                        name_zh: ing.name_zh,
                        weight_g: Number(ing.weight_g) || 0,
                        weight_method: ing.weight_method,
                        data_source: ing.data_source,
                        energy_kj: Math.round(this.kcalToKJ(this.macrosToKcal(
                            ing.macros?.protein_g,
                            ing.macros?.fat_g,
                            ing.macros?.carbs_g
                        )) * 1000) / 1000,
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

            // B. 用户新增菜式：用单一 ingredient 表示（结构保持一致）
            return {
                standard_name: d.name,
                ingredients: [
                    {
                        name_zh: d.name,
                        weight_g: Number(d.weight) || 0,
                        weight_method: "user_edit",
                        data_source: "user_edit",
                        energy_kj: Math.round(this.kcalToKJ(this.macrosToKcal(d.protein, d.fat, d.carb)) * 1000) / 1000,
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

        return {
            meal_summary: {
                meal_name: mealName,
                diet_time: dietTime,
                total_energy_kj: Math.round(this.kcalToKJ(totalEnergyKcal) * 1000) / 1000,
                total_protein_g: Number(totals.totalProtein) || 0,
                total_fat_g: Number(totals.totalFat) || 0,
                total_carbs_g: Number(totals.totalCarb) || 0,
                total_fiber_g: Number(totals.totalFiber) || 0,
                total_sodium_mg: Number(totals.totalSodiumMg) || 0,
            },
            dishes: editedDishes,
            captured_labels: editedLabels,
            // AI 识别的发生时间
            occurred_at: this.currentDietMeta?.occurredAt || null,
        };
    },

    getDishTotals(dish) {
        // AI：按 ingredients 加总；User：按 dish 汇总字段
        if (dish?.source === 'ai') {
            const ings = dish.ingredients || [];
            const sum = (fn) => ings.reduce((a, x) => a + (fn(x) || 0), 0);
            const w = sum(x => Number(x.weight_g) || 0);
            const p = sum(x => Number(x.macros?.protein_g) || 0);
            const f = sum(x => Number(x.macros?.fat_g) || 0);
            const c = sum(x => Number(x.macros?.carbs_g) || 0);
            const fib = sum(x => Number(x.macros?.fiber_g) || 0);
            const na = sum(x => Number(x.macros?.sodium_mg) || 0);
            return {
                weight: Math.round(w * 10) / 10,
                protein: Math.round(p * 10) / 10,
                fat: Math.round(f * 10) / 10,
                carb: Math.round(c * 10) / 10,
                fiber: Math.round(fib * 10) / 10,
                sodium_mg: Math.round(na),
            };
        }
        return {
            weight: Math.round((Number(dish?.weight) || 0) * 10) / 10,
            protein: Math.round((Number(dish?.protein) || 0) * 10) / 10,
            fat: Math.round((Number(dish?.fat) || 0) * 10) / 10,
            carb: Math.round((Number(dish?.carb) || 0) * 10) / 10,
            fiber: Math.round((Number(dish?.fiber) || 0) * 10) / 10,
            sodium_mg: Math.round(Number(dish?.sodium_mg) || 0),
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
