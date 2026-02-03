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
        this.updateStatus('modified');
        this.updateButtonStates(this.currentSession);
    },

    collectEditedData() {
        // [Fix] Dependency on 'this.mode' caused issue when input mode switched.
        // Use session mode as source of truth.
        const sessionMode = this.currentSession?.mode;
        // 只要是 diet 或者拥有有效 diet 数据（dishes 不为空），就应该允许收集，防止 Input Mode 切换（Advice Mode）导致数据丢失
        const hasData = this.currentDishes && this.currentDishes.length > 0;

        if (sessionMode !== 'diet' && !hasData) return {};

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
            captured_labels: editedLabels,
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
            const rect = inputElement.getBoundingClientRect();
            resultsPanel.style.top = `${rect.bottom + window.scrollY + 5}px`;
            resultsPanel.style.left = `${rect.left + window.scrollX}px`;
            resultsPanel.style.width = `${Math.max(rect.width, 300)}px`; // Min width
            resultsPanel.style.right = 'auto';
        });

        inputElement.dataset.searchBound = "true";
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
