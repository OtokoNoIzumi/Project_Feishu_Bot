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
            if (isCollapsed) {
                this.renderLabelsSection();
            }
        }
    },

    // 更新营养标签字段
    updateLabel(index, field, value) {
        if (this.currentLabels && this.currentLabels[index]) {
            const oldValue = this.currentLabels[index][field];
            this.currentLabels[index][field] = value;


            this.markModified();

            // 联动更新：如果修改的是产品名称，且有 Dish/Ingredient 名称匹配，则一并更新
            if (field === 'productName' && oldValue && oldValue !== value && this.currentDishes) {
                this.currentDishes.forEach((dish, dIdx) => {
                    // 1. 检查 Dish Name
                    // 注意：dish.name 来自 standard_name
                    if (dish.name === oldValue) {
                        dish.name = value;
                        if (dish.standard_name) dish.standard_name = value;

                        // Update DOM: Editable Name
                        const dishNameSpan = document.querySelector(`.editable-name[data-type="dish"][data-index="${dIdx}"] .editable-name-text`);
                        if (dishNameSpan) {
                            dishNameSpan.textContent = value;
                        }
                    } else if (dish.standard_name === oldValue) {
                        // Fallback check if name and standard_name diverged
                        dish.standard_name = value;
                        // 这里如果不更新 dish.name，可能会导致后续不一致，建议保持一致
                        if (dish.name === oldValue) dish.name = value;
                    }

                    // 2. 检查 Ingredients
                    if (dish.ingredients) {
                        dish.ingredients.forEach((ing, iIdx) => {
                            if (ing.name_zh === oldValue) {
                                ing.name_zh = value;
                                // Update DOM: Ingredient Name Input (Readonly)
                                // Selector: .diet-dish-block[data-dish-index="..."] tr[data-ing-index="..."] td input
                                const ingInput = document.querySelector(`.diet-dish-block[data-dish-index="${dIdx}"] tr[data-ing-index="${iIdx}"] td:first-child input`);
                                if (ingInput) {
                                    ingInput.value = value;
                                }
                            }
                        });
                    }
                });
            }
        }
    },

    // 更新餐食类型（对应下拉框）
    updateMealType(newTimeKey, newName) {
        if (!this.currentDietMeta) return;
        this.currentDietMeta.mealName = newName; // 存储中文显示名 (e.g. "晚餐")
        this.currentDietMeta.dietTime = newTimeKey; // 存储枚举 Key (e.g. "dinner")
        this.markModified();
    },

    updateDish(index, field, value) {
        if (this.currentDishes && this.currentDishes[index]) {
            const dish = this.currentDishes[index];
            // AI 菜式：菜式层级不可编辑（只允许编辑 ingredients）
            if (dish.source === 'ai') {
                return;
            }

            const numVal = parseFloat(value) || 0;
            dish[field] = field === 'name' ? value : numVal;

            // Weight-Bound Logic (Search Result Mode)
            if (dish._weightBound && dish._macrosPer100g && field === 'weight') {
                const ratio = numVal / 100;
                const m = dish._macrosPer100g;
                dish.protein = Math.round(m.protein_g * ratio * 10) / 10;
                dish.fat = Math.round(m.fat_g * ratio * 10) / 10;
                dish.carb = Math.round(m.carbs_g * ratio * 10) / 10;
                dish.fiber = Math.round(m.fiber_g * ratio * 10) / 10;
                dish.sodium_mg = Math.round(m.sodium_mg * ratio);
                // Force update DOM for these fields
                this.updateDishRowDOM(index); // This only does energy, need full update?
                // renderDietDishes might be too heavy? 
                // updateDishRowDOM only updates energy. I need to update inputs values too.
                // Let's do a full re-render for now or manual update.
                // Manual update is better for focus.
                setTimeout(() => this.syncDishRowInputs(index), 0);
            } else if (dish._weightBound && field !== 'name' && field !== 'weight') {
                // User manually edited a macro => Update density (re-bind to new density)
                // or just keep it bound?
                // Let's update _macrosPer100g to reflect new density if weight > 0
                if (dish.weight > 0) {
                    const factor = 100 / dish.weight;
                    dish._macrosPer100g = dish._macrosPer100g || {};
                    // Map field 'carb' -> 'carbs_g' etc.
                    const map = { 'protein': 'protein_g', 'fat': 'fat_g', 'carb': 'carbs_g', 'fiber': 'fiber_g', 'sodium_mg': 'sodium_mg' };
                    if (map[field]) {
                        dish._macrosPer100g[map[field]] = numVal * factor;
                    }
                }
            }

            this.recalculateDietSummary(true);

            // 优化：仅更新当前行 DOM，不重绘整个列表以保持焦点 (except if bound update happened)
            if (!dish._weightBound || field !== 'weight') {
                this.updateDishRowDOM(index);
            }
        }
    },

    syncDishRowInputs(index) {
        const dish = this.currentDishes[index];
        const row = document.querySelector(`tr[data-dish-index="${index}"]`);
        if (!row || !dish) return;

        const setVal = (f, v) => {
            const el = row.querySelector(`input[oninput*="'${f}'"]`);
            if (el) el.value = v;
        }
        setVal('protein', dish.protein);
        setVal('fat', dish.fat);
        setVal('carb', dish.carb);
        setVal('fiber', dish.fiber);
        setVal('sodium_mg', dish.sodium_mg);

        // Update energy display
        const energyText = this.formatEnergyFromMacros(dish.protein, dish.fat, dish.carb);
        const energyInput = row.querySelector('.js-energy-display');
        if (energyInput) energyInput.value = energyText;
    },

    /**
     * 更新菜式名称（支持 AI 和用户菜式）
     * 由 EditableNameModule 调用
     */
    updateDishName(index, newName) {
        if (!this.currentDishes || !this.currentDishes[index]) return;

        const dish = this.currentDishes[index];
        dish.name = newName;

        // 标记已修改
        this.markModified();

        // 重新渲染菜式列表
        this.renderDietDishes();
    },

    /**
     * 更新 Meal 名称（卡片顶部标题）
     * 由 EditableNameModule 调用
     */
    updateMealName(newName) {
        if (!this.currentDietMeta) return;

        this.currentDietMeta.userMealName = newName;

        // 标记已修改
        this.markModified();
    },

    updateIngredient(dishIndex, ingIndex, field, value) {
        const dish = this.currentDishes?.[dishIndex];
        if (!dish || dish.source !== 'ai') return;
        const ing = dish.ingredients?.[ingIndex];
        if (!ing) return;

        if (field === 'name_zh') {
            ing.name_zh = value;
            this.markModified();
            return;
        }

        if (field === 'weight_g') {
            const newWeight = parseFloat(value) || 0;
            // 如果开启了等比缩放且有密度数据，按比例调整所有营养素
            if (ing._proportionalScale && ing._density && newWeight > 0) {
                // [Fix] Ensure energy_per_g exists in density (handling legacy data state)
                if (ing._density.energy_per_g === undefined && ing.weight_g > 0 && ing.energy_kj !== undefined) {
                    ing._density.energy_per_g = ing.energy_kj / ing.weight_g;
                }

                ing.macros.protein_g = Math.round(ing._density.protein_per_g * newWeight * 100) / 100;
                ing.macros.fat_g = Math.round(ing._density.fat_per_g * newWeight * 100) / 100;
                ing.macros.carbs_g = Math.round(ing._density.carbs_per_g * newWeight * 100) / 100;
                ing.macros.sodium_mg = Math.round(ing._density.sodium_per_g * newWeight * 100) / 100;
                ing.macros.fiber_g = Math.round(ing._density.fiber_per_g * newWeight * 100) / 100;

                // Update Energy if density exists
                if (ing._density.energy_per_g) {
                    ing.energy_kj = Math.round(ing._density.energy_per_g * newWeight * 10) / 10;
                }
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

                // [Fix] Recalculate energy_kj when macros change
                const newKcal = EnergyUtils.macrosToKcal(
                    ing.macros.protein_g,
                    ing.macros.fat_g,
                    ing.macros.carbs_g
                );
                ing.energy_kj = Math.round(EnergyUtils.kcalToKJ(newKcal) * 10) / 10;

                // Update energy density as well
                ing._density.energy_per_g = ing.energy_kj / ing.weight_g;
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

    // 快捷修改重量 (Quick Record Inline Edit)
    updateQuickWeight(dishIdx, ingIdx, value) {
        const dish = this.currentDishes?.[dishIdx];
        if (!dish || !dish.ingredients) return;
        const ing = dish.ingredients[ingIdx];
        if (!ing) return;

        // Force Proportional Mode
        ing._proportionalScale = true;

        // Ensure density exists
        if (!ing._density && Number(ing.weight_g) > 0) {
            const m = ing.macros || {};
            const w = Number(ing.weight_g);
            ing._density = {
                protein_per_g: (Number(m.protein_g) || 0) / w,
                fat_per_g: (Number(m.fat_g) || 0) / w,
                carbs_per_g: (Number(m.carbs_g) || 0) / w,
                sodium_per_g: (Number(m.sodium_mg) || 0) / w,
                fiber_per_g: (Number(m.fiber_g) || 0) / w,
                energy_per_g: (Number(ing.energy_kj) || 0) / w
            };
        }

        // Call Standard Update (Updates Model + Recalculates Totals)
        this.updateIngredient(dishIdx, ingIdx, 'weight_g', value);

        // Manual DOM Update for List (to avoid full re-render losing focus)
        const card = document.querySelector(`.mobile-dish-card[data-dish-index="${dishIdx}"][data-ing-index="${ingIdx}"]`);
        if (card) {
            const r = (n) => Math.round(n * 10) / 10;
            const m = ing.macros || {};
            const macrosSpan = card.querySelector('.js-mobile-macros');
            if (macrosSpan) {
                macrosSpan.textContent = `蛋白:${r(m.protein_g)} 脂肪:${r(m.fat_g)} 碳水:${r(m.carbs_g)}`;
            }
            const energySpan = card.querySelector('.js-mobile-energy');
            if (energySpan) {
                const unit = this.getEnergyUnit();
                energySpan.textContent = `${this.formatEnergyFromMacros(m.protein_g, m.fat_g, m.carbs_g)} ${unit}`;
            }
        }
    },

    // 委托给 EnergyUtils (为了方便内部调用)
    formatEnergyFromMacros(p, f, c) {
        return EnergyUtils.formatEnergyFromMacros(p, f, c, this.getEnergyUnit());
    },

    // 获取当前能量单位 - 【重构】统一使用 ProfileModule 作为唯一数据源
    // 获取当前能量单位 - 【重构】统一使用 ProfileModule 作为唯一数据源
    getEnergyUnit() {
        return (ProfileModule.getCurrentProfile()?.diet?.energy_unit) || 'kJ';
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
                // Add energy density
                energy_per_g: (ing.energy_kj || 0) / ing.weight_g,
            };
        }

        this.renderDietDishes();
    },

    addDish() {
        if (!this.currentDishes) this.currentDishes = [];
        this.currentDishes.push({
            name: '',
            weight: 100,
            protein: 0,
            fat: 0,
            carb: 0,
            fiber: 0,
            sodium_mg: 0,
            source: 'user', // 标记为用户手动添加
            enabled: true,
            _weightBound: false // Default to custom mode
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

        setText('sum-total-weight', this.currentDietTotals.totalWeightG);

        // [Opt] 精细更新副标题，防止覆盖下拉框
        const countSpan = document.getElementById('diet-dish-count');
        if (countSpan) {
            countSpan.textContent = `${dishes.length} 种食物`;
        } else {
            // Fallback for legacy structure (or if render hasn't run new logic yet)
            const subtitle = document.getElementById('diet-subtitle');
            if (subtitle && this.currentDietMeta) {
                // 注意：这里可能会覆盖掉 selector，仅作为兜底
                // 为防止闪烁，尽量在 render 时就生成好结构
                // subtitle.textContent = ...
            }
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
        const ctx = (this && typeof this.updateStatus === 'function') ? this : window.Dashboard;
        if (ctx && typeof ctx.updateStatus === 'function') {
            ctx.updateStatus('modified');
        }
        if (ctx && typeof ctx.updateButtonStates === 'function') {
            ctx.updateButtonStates(ctx.currentSession || this.currentSession);
        }
    },

    renderLabelsSection() {
        const container = document.getElementById('labels-content');
        if (!container) return;

        this.currentLabels = this.currentLabels || [];
        if (this.currentLabels.length === 0) {
            container.innerHTML = '<div class="empty-hint">无营养标签数据</div>';
            return;
        }

        const safe = (v) => (v === undefined || v === null) ? '' : v;

        container.innerHTML = this.currentLabels.map((lb, idx) => {
            // Map legacy fields to new structure if needed
            const tableUnit = lb.tableUnit || lb.table_unit || 'g';
            const tableAmount = Number(lb.tableAmount || lb.table_amount) || 100;
            const unitWeightG = Number(lb.unitWeightG || lb.unit_weight_g) || '';
            const densityFactor = (lb.densityFactor ?? lb.density_factor ?? 1.0);

            return `
              <div class="label-card label-input-row" data-label-index="${idx}">
                <div class="label-edit-row">
                  <div class="label-edit-field label-edit-primary">
                    <label>产品名称</label>
                    <input type="text" class="label-input label-name" value="${safe(lb.productName || lb.product_name)}" placeholder="产品名称" oninput="Dashboard.updateLabel(${idx}, 'productName', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>品牌</label>
                    <input type="text" class="label-input label-brand" value="${safe(lb.brand)}" placeholder="品牌" oninput="Dashboard.updateLabel(${idx}, 'brand', this.value)" onfocus="this.select()">
                  </div>
                </div>
                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>规格/口味</label>
                    <input type="text" class="label-input label-variant" value="${safe(lb.variant)}" placeholder="如：无糖/低脂" oninput="Dashboard.updateLabel(${idx}, 'variant', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>单件重量(g)</label>
                    <input type="number" class="label-input label-unit-weight" value="${unitWeightG}" placeholder="非必填" oninput="Dashboard.updateLabel(${idx}, 'unitWeightG', this.value)" onfocus="this.select()">
                  </div>
                </div>

                <div class="label-section-title">营养成分表</div>

                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>单位</label>
                    <input type="text" class="label-input label-table-unit" value="${safe(tableUnit)}" placeholder="如 g, ml, 份" oninput="Dashboard.updateLabel(${idx}, 'tableUnit', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>计量</label>
                    <input type="number" class="label-input label-input-sm label-table-amount" value="${tableAmount}" min="0" step="0.1" oninput="Dashboard.updateLabel(${idx}, 'tableAmount', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label class="label-with-tooltip">
                        换算系数
                        <span class="info-icon" title="用来把单位换算到重量的系数&#10;例如密度1.023g/ml 填 1.023">?</span>
                    </label>
                    <input type="number" class="label-input label-input-sm label-density" value="${safe(densityFactor)}" min="0" step="0.001" oninput="Dashboard.updateLabel(${idx}, 'densityFactor', this.value)" onfocus="this.select()">
                  </div>
                </div>
                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>能量(kJ)</label>
                    <input type="number" class="label-input label-energy" value="${safe(lb.energyKjPerServing || lb.energy_value || 0)}" oninput="Dashboard.updateLabel(${idx}, 'energyKjPerServing', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>蛋白(g)</label>
                    <input type="number" class="label-input label-protein" value="${safe(lb.proteinGPerServing || lb.protein_g || 0)}" step="0.1" oninput="Dashboard.updateLabel(${idx}, 'proteinGPerServing', this.value)" onfocus="this.select()">
                  </div>
                </div>
                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>脂肪(g)</label>
                    <input type="number" class="label-input label-fat" value="${safe(lb.fatGPerServing || lb.fat_g || 0)}" step="0.1" oninput="Dashboard.updateLabel(${idx}, 'fatGPerServing', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>碳水(g)</label>
                    <input type="number" class="label-input label-carbs" value="${safe(lb.carbsGPerServing || lb.carbs_g || 0)}" step="0.1" oninput="Dashboard.updateLabel(${idx}, 'carbsGPerServing', this.value)" onfocus="this.select()">
                  </div>
                </div>
                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>钠(mg)</label>
                    <input type="number" class="label-input label-sodium" value="${safe(lb.sodiumMgPerServing || lb.sodium_mg || 0)}" oninput="Dashboard.updateLabel(${idx}, 'sodiumMgPerServing', this.value)" onfocus="this.select()">
                  </div>
                  <div class="label-edit-field">
                    <label>纤维(g)</label>
                    <input type="number" class="label-input label-fiber" value="${safe(lb.fiberGPerServing || lb.fiber_g || 0)}" step="0.1" oninput="Dashboard.updateLabel(${idx}, 'fiberGPerServing', this.value)" onfocus="this.select()">
                  </div>
                </div>
                <div class="label-edit-field label-edit-full">
                  <label>备注</label>
                  <input type="text" class="label-input label-note" value="${safe(lb.customNote || lb.custom_note)}" placeholder="如：产地/版本/渠道等" oninput="Dashboard.updateLabel(${idx}, 'customNote', this.value)" onfocus="this.select()">
                </div>
              </div>
            `;
        }).join('');
    },

    collectEditedData() {
        // [Fix] Dependency on 'this.mode' caused issue when input mode switched.
        // Use session mode as source of truth.
        const sessionMode = this.currentSession?.mode;
        // 只要是 diet 或者拥有有效 diet 数据（dishes 不为空），就应该允许收集，防止 Input Mode 切换（Advice Mode）导致数据丢失
        const hasData = this.currentDishes && this.currentDishes.length > 0;

        // Logic check: Allow 'diet' mode OR if it has effective data (e.g. implicitly editing diet in advice mode)
        // However, if we are in 'advice' mode, we usually don't trigger collectEditedData unless we are "Saving to Diet Log".
        // The problem reported is "Input should be 'diet' or 'keep'". This logic here just collects data.
        // The requester (save logic) uses this data.

        // If sessionMode is not diet, but we have data, we should allow collection.
        if (sessionMode !== 'diet' && !hasData) return {};
        // But wait, if mode is 'advice', we shouldn't be collecting diet data for saving as a "diet_log" record 
        // unless we implicitly converted it?
        // The error 'Input should be diet or keep' comes from backend schema validation for `mode`.
        // The API call uses `this.currentSession.mode` as the mode field in payload (via api.js/dashboard.js logic).
        // If currentSession.mode is "advice", the backend rejects it because record creation must be 'diet' or 'keep'.
        // 
        // Fix: Force mode to 'diet' for the collected data payload if we are saving diet data.
        // The actual session object in memory can stay as 'advice' if needed, but the PAYLOAD sent to API must be compliant.

        if (!this.currentDietTotals) {
            this.recalculateDietSummary(false);
        }

        const totals = this.currentDietTotals || {};
        const mealName = this.currentDietMeta?.mealName || '饮食记录';
        const dietTime = this.currentDietMeta?.dietTime || '';
        const ExtraImageSummary = this.currentSession?.versions[this.currentSession.currentVersion - 1]?.parsedData?.extraImageSummary || '';

        // 核心：在编辑模式下，必须传递 saved_record_id 给后端，以便后端在计算 "Used Context" 时排除掉这个旧版本
        // 从而避免 "今日摄入" 重复计算 (Double Counting) 和 "历史记录" 重复展示
        const savedRecordId = this.currentSession.savedRecordId || null;

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
                        weight_method: 'user_edit',
                        data_source: 'user_edit',
                        // Calculate energy for user dish from macros
                        energy_kj: this.getDishTotals(d).energy_kj,
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

        // 收集编辑后的营养标签 (UI Visible)
        // [Refactor] Read directly from Input DOMs if available to support full editing
        const editedLabels = [];
        const labelRows = document.querySelectorAll('.label-input-row');

        if (labelRows.length > 0) {
            // Priority: Read from DOM
            labelRows.forEach(row => {
                const getVal = (cls) => row.querySelector(`.${cls}`)?.value;
                const getNum = (cls) => parseFloat(getVal(cls)) || 0;
                // Read new structure
                const tableUnit = getVal('label-table-unit') || 'g';
                const tableAmount = getNum('label-table-amount') || 100;
                const unitWeightG = getNum('label-unit-weight') || 0;

                editedLabels.push({
                    product_name: getVal('label-name') || '',
                    brand: getVal('label-brand') || '',
                    variant: getVal('label-variant') || '',
                    unit_weight_g: unitWeightG, // New field matches backend
                    table_unit: tableUnit,       // New field
                    table_amount: tableAmount,   // New field

                    density_factor: getNum('label-density') || 1.0,
                    energy_kj_per_serving: getNum('label-energy'),
                    protein_g_per_serving: getNum('label-protein'),
                    fat_g_per_serving: getNum('label-fat'),
                    carbs_g_per_serving: getNum('label-carbs'),
                    sodium_mg_per_serving: getNum('label-sodium'),
                    fiber_g_per_serving: getNum('label-fiber'),
                    custom_note: getVal('label-note') || '',
                });
            });
        } else {
            // Fallback: Read from memory if UI not rendered
            (this.currentLabels || []).forEach(lb => {
                const tableUnit = lb.tableUnit || lb.table_unit || 'g';
                const tableAmount = Number(lb.tableAmount || lb.table_amount) || 100;

                editedLabels.push({
                    product_name: lb.productName || lb.product_name || '',
                    brand: lb.brand || '',
                    variant: lb.variant || '',
                    unit_weight_g: Number(lb.unitWeightG || lb.unit_weight_g) || 0,
                    table_unit: tableUnit,
                    table_amount: tableAmount,
                    density_factor: Number(lb.densityFactor ?? lb.density_factor ?? 1.0),
                    energy_kj_per_serving: Number(lb.energyKjPerServing || lb.energy_value || 0),
                    protein_g_per_serving: Number(lb.proteinGPerServing || lb.protein_g || 0),
                    fat_g_per_serving: Number(lb.fatGPerServing || lb.fat_g || 0),
                    carbs_g_per_serving: Number(lb.carbsGPerServing || lb.carbs_g || 0),
                    sodium_mg_per_serving: Number(lb.sodiumMgPerServing || lb.sodium_mg || 0),
                    fiber_g_per_serving: Number(lb.fiberGPerServing || lb.fiber_g || 0),
                    custom_note: lb.customNote || lb.custom_note || ''
                });
            });
        }

        // [New] Collect Implicitly Used Products for Reordering/Upsert (Smart Deduplication)
        // We use a Map to keep unique products by key, ensuring valid product data.

        const implicitProductsMap = new Map();

        const addImplicit = (prod) => {
            if (!prod || !prod.product_name) return; // Basic validation
            const key = `${prod.brand || ''}|${prod.product_name}|${prod.variant || ''}`;
            implicitProductsMap.set(key, prod);
        };

        (this.currentDishes || []).forEach(d => {
            if (d.enabled === false) return;

            // 1. Dish itself (e.g. Added via "Add Dish" -> "Product Search")
            if (d._productMeta && d._productMeta.raw_data) {
                addImplicit(d._productMeta.raw_data);
            }

            // 2. Ingredients (e.g. Edited via "Ingredient" -> "Product Search")
            if (d.ingredients) {
                d.ingredients.forEach(ing => {
                    if (ing._productMeta && ing._productMeta.raw_data) {
                        addImplicit(ing._productMeta.raw_data);
                    }
                });
            }
        });

        // Merge into editedLabels
        const existingKeys = new Set(editedLabels.map(l => `${l.brand || ''}|${l.product_name || l.name || ''}|${l.variant || ''}`));

        implicitProductsMap.forEach((prod, key) => {
            if (!existingKeys.has(key)) {
                const normalized = {
                    product_name: prod.product_name || prod.name || '',
                    brand: prod.brand || '',
                    variant: prod.variant || '',
                    table_unit: prod.table_unit || 'g',
                    table_amount: Number(prod.table_amount) || 100,
                    density_factor: Number(prod.density_factor || prod.density) || 1.0,
                    energy_kj_per_serving: Number(prod.energy_kj_per_serving || prod.energy_kj) || 0,
                    protein_g_per_serving: Number(prod.protein_g_per_serving || prod.protein_g) || 0,
                    fat_g_per_serving: Number(prod.fat_g_per_serving || prod.fat_g) || 0,
                    carbs_g_per_serving: Number(prod.carbs_g_per_serving || prod.carbs_g) || 0,
                    sodium_mg_per_serving: Number(prod.sodium_mg_per_serving || prod.sodium_mg) || 0,
                    fiber_g_per_serving: Number(prod.fiber_g_per_serving || prod.fiber_g) || 0,
                    custom_note: prod.custom_note || '',
                };

                editedLabels.push(normalized);
                existingKeys.add(key);
            }
        });

        // 2. 构造并合并返回对象
        // 优先级：编辑后的数据 > 原始数据
        return {
            // isSaved: saved, // Removed: API logic relies on saved_record_id, no need to send UI state
            saved_record_id: savedRecordId, // <--- 新增核心字段
            is_quick_record: !!this.currentSession?.isQuickRecord,
            meal_summary: {
                meal_name: mealName,
                user_meal_name: this.currentDietMeta?.userMealName || null,
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
            captured_labels: editedLabels, // Now includes implicit products too
            extra_image_summary: ExtraImageSummary,
            occurred_at: this.currentDietMeta?.occurredAt || null,
        };
    },

    // --- Search Integration ---

    bindDishSearch(inputElement, index) {
        if (!inputElement || inputElement.dataset.searchBound) return;

        // Dynamic Popup Container
        let resultsPanel = document.getElementById('diet-dish-search-popup');
        if (!resultsPanel) {
            resultsPanel = document.createElement('div');
            resultsPanel.id = 'diet-dish-search-popup';
            resultsPanel.className = 'editable-name-suggestions';
            document.body.appendChild(resultsPanel);
        }

        const controller = new SearchController({
            input: inputElement,
            resultsPanel: resultsPanel,
            mode: 'dish',
            onSelect: (item) => {
                console.log('[AddDish_debug] select', { index, item });
                this.updateDishFromSearch(index, item);
            }
        });
        SearchController.register(controller);

        // Logic to position the popup
        inputElement.addEventListener('focus', () => {
            // ... logic same as existing ...
            this.repositionPopup(inputElement, resultsPanel);
        });

        // Debounced reposition recalculation on window resize? Not strictly needed for now.

        inputElement.dataset.searchBound = "true";
    },

    bindIngredientSearch(inputElement, dishIndex, ingIndex) {
        if (!inputElement || inputElement.dataset.searchBound) return;

        let resultsPanel = document.getElementById('diet-dish-search-popup'); // Reuse same popup
        if (!resultsPanel) {
            resultsPanel = document.createElement('div');
            resultsPanel.id = 'diet-dish-search-popup';
            resultsPanel.className = 'editable-name-suggestions';
            document.body.appendChild(resultsPanel);
        }

        const controller = new SearchController({
            input: inputElement,
            resultsPanel: resultsPanel,
            mode: 'product', // Filter by product for ingredients
            onSelect: (item) => {
                this.updateIngredientFromSearch(dishIndex, ingIndex, item);
            }
        });
        SearchController.register(controller);

        inputElement.addEventListener('focus', () => {
            this.repositionPopup(inputElement, resultsPanel);
        });
        inputElement.dataset.searchBound = "true";
    },

    repositionPopup(input, panel) {
        const rect = input.getBoundingClientRect();
        panel.style.top = `${rect.bottom + window.scrollY + 5}px`;
        panel.style.left = `${rect.left + window.scrollX}px`;
        panel.style.width = `${Math.max(rect.width, 300)}px`;
        panel.style.right = 'auto';
    },

    updateIngredientFromSearch(dishIdx, ingIdx, item) {
        if (!window.SearchController || !item) return;
        const dish = this.currentDishes?.[dishIdx];
        if (!dish || !dish.ingredients) return;
        const ing = dish.ingredients[ingIdx];
        if (!ing) return;

        const data = item.data || {};
        // Only Products supported
        if (item.type !== 'product') return;

        const name = data.product_name || data.name || ing.name_zh;

        // Keep current weight, but update macros based on product density
        const currentWeight = Number(ing.weight_g) || 100;
        const macros = SearchController.extractMacrosPer100g(data);

        // Consistent rounding helpers
        const r1 = (v) => Math.round((Number(v) || 0) * 10) / 10;
        const r0 = (v) => Math.round(Number(v) || 0);

        const calculate = (val100) => (Number(val100) * currentWeight / 100);

        ing.name_zh = name;
        // Apply consistent rounding (1 decimal for macros, 0 for sodium/energy usually? Or consistent r1/r0)
        // SearchController uses r1 for P/F/C/Fib and r0 for Sodium.
        ing.macros.protein_g = r1(calculate(macros.protein_g));
        ing.macros.fat_g = r1(calculate(macros.fat_g));
        ing.macros.carbs_g = r1(calculate(macros.carbs_g));
        ing.macros.fiber_g = r1(calculate(macros.fiber_g));
        ing.macros.sodium_mg = r0(calculate(macros.sodium_mg));

        // Recalc energy (prefer label energy if present)
        const energyKj100 = SearchController.extractEnergyPer100g(data, macros);
        ing.energy_kj = r0(energyKj100 * currentWeight / 100);

        // Update density for proportional scaling
        // Density uses raw precision for internal scaling calculation
        ing._density = {
            protein_per_g: macros.protein_g / 100,
            fat_per_g: macros.fat_g / 100,
            carbs_per_g: macros.carbs_g / 100,
            sodium_per_g: macros.sodium_mg / 100,
            fiber_per_g: macros.fiber_g / 100,
            energy_per_g: (energyKj100 / 100)
        };

        // Store Product Meta for Recency/Upsert
        ing._productMeta = {
            product_name: data.product_name || data.name || ing.name_zh,
            brand: data.brand || '',
            variant: data.variant || '',
            table_unit: data.table_unit || 'g',
            // Store original macros per serving if available, or just rely on what we have?
            // Ideally we want the exact product object.
            // Let's store a snapshot or just the keys needed for upsert?
            // Backend Upsert needs: brand, product_name, variant, + all macro fields.
            // Let's store the raw data simply to replay it.
            raw_data: data
        };

        this.recalculateDietSummary(true);
        this.renderDietDishes(); // Re-render to update all fields
        this.markModified();
    },

    // Helper reused
    calcEnergyKJ(macros) {
        const p = parseFloat(macros.protein_g || 0);
        const f = parseFloat(macros.fat_g || 0);
        const c = parseFloat(macros.carbs_g || 0);
        const kcal = (p * 4) + (f * 9) + (c * 4);
        return kcal * 4.184;
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

    updateDishFromSearch(index, item) {
        if (!window.SearchController) return;
        const updated = SearchController.applyAddDishSelection(this, index, item);
        if (!updated) return;

        // Enable Weight Bound Mode
        const dish = this.currentDishes && this.currentDishes[index];
        if (dish) {
            dish._weightBound = true;
            const data = item.data || {};
            dish._macrosPer100g = SearchController.extractMacrosPer100g(data);
            dish._energyPer100g = SearchController.extractEnergyPer100g(data, dish._macrosPer100g);

            dish._productMeta = {
                product_name: data.product_name || data.name || dish.name,
                brand: data.brand || '',
                variant: data.variant || '',
                table_unit: data.table_unit || 'g',
                raw_data: data
            };
        }

        this.recalculateDietSummary(true);
        this.renderDietDishes();
        this.markModified();
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
