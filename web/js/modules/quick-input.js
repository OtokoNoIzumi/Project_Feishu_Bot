/**
 * Quick Input Module
 * Ref: web/js/modules/quick-input.js
 * 
 * Handles layout and logic for the "Quick Record" feature.
 * Now supports managing "Favorite" cards and executing them as templates.
 */

const QuickInputModule = {
    // Defines available templates (Legacy / Fallback)
    _defaultTemplates: [
        {
            id: 'oat_skim_milk_demo',
            name: '燕麦脱脂奶 (示例)',
            mealtimes: ['breakfast', 'snack'],
            ingredients: [
                {
                    name: '燕麦',
                    default_weight: 0,
                    // Macros per 100g
                    per_100g: {
                        calories: 389,
                        protein: 16.9,
                        fat: 6.9,
                        carbs: 66.0,
                        sodium: 4,
                        fiber: 10
                    }
                },
                {
                    name: '脱脂牛奶',
                    default_weight: 0,
                    per_100g: {
                        calories: 35,
                        protein: 3.4,
                        fat: 0.1,
                        carbs: 5.0,
                        sodium: 40,
                        fiber: 0
                    }
                }
            ]
        }
    ],

    templates: [], // Local cache of favorites

    async init() {
        try {
            // Load from Backend
            this.templates = await API.getDietTemplates();
            if (window.SidebarModule) window.SidebarModule.refreshFavorites();
        } catch (e) {
            console.error('[QuickInput] Failed to load templates:', e);
            // Fallback to empty
            this.templates = [];
        }
    },

    /**
     * Entry point for Quick Input flow
     */
    start() {
        const favorites = this.getFavorites();
        if (favorites.length > 0) {
            this.executeFavorite(favorites[0].id);
        } else {
            // Use default template logic if no favorites
            this.applyTemplate(this._defaultTemplates[0]);
        }
    },

    // ================= Storage Logic =================

    getFavorites() {
        return this.templates || [];
    },

    isFavorite(sessionId) {
        if (!sessionId) return false;
        const list = this.getFavorites();
        return list.some(item => item.id === sessionId);
    },

    toggleFavorite(session) {
        if (!session || !session.id) return;
        const list = this.getFavorites();
        const index = list.findIndex(item => item.id === session.id);

        if (index >= 0) {
            // Remove via API
            const tId = this.templates[index].id;
            API.deleteDietTemplate(tId).then(() => {
                this.templates.splice(index, 1);
                if (window.ToastUtils) ToastUtils.show('已取消收藏', 'info');

                if (window.SidebarModule) window.SidebarModule.refreshFavorites();
                if (window.Dashboard) window.Dashboard.renderResult(session);
            }).catch(e => {
                console.error('[QuickInput] Delete failed', e);
                if (window.ToastUtils) ToastUtils.show('取消失败', 'error');
            });
        } else {
            console.log('[QuickInput] Adding favorite. Session:', session);
            // Add
            let title = '未命名餐食';
            let summaryInfo = { energy: 0, weight: 0 };
            let rawDishes = [];

            // --- DATA EXTRACTION STRATEGY ---
            // 1. parsedData (Fresh Analysis)
            // 2. savedData (Re-loaded Saved Card)
            // 3. versions (Fallback)

            let sourceSummary = null;
            let sourceDishes = null;
            let sourceTitleRaw = null;

            if (session.parsedData) {
                // Case A: Fresh Analysis
                sourceDishes = session.parsedData.dishes;
                sourceSummary = session.parsedData.summary;
                sourceTitleRaw = session.parsedData.title;
            } else if (session.savedData) {
                // Case B: Saved Card (snake_case from backend)
                console.log('[QuickInput] Using savedData');
                sourceDishes = session.savedData.dishes;
                if (session.savedData.meal_summary) {
                    sourceSummary = {
                        totalEnergy: session.savedData.meal_summary.total_energy_kj, // Mapping snake to camel-ish usage or just value
                        total_energy_kj: session.savedData.meal_summary.total_energy_kj
                    };
                }
                sourceTitleRaw = session.savedData.title; // Card title
            } else if (session.versions && session.versions.length > 0) {
                // Case C: Look into versions
                const ver = session.versions[session.currentVersion - 1] || session.versions[session.versions.length - 1];
                if (ver) {
                    if (ver.parsedData) {
                        sourceDishes = ver.parsedData.dishes;
                        sourceSummary = ver.parsedData.summary;
                        sourceTitleRaw = ver.parsedData.title;
                    } else if (ver.rawResult) {
                        sourceDishes = ver.rawResult.dishes;
                        sourceSummary = ver.rawResult.meal_summary ? {
                            totalEnergy: ver.rawResult.meal_summary.total_energy_kj
                        } : null;
                    }
                }
            }

            if (sourceDishes) {
                rawDishes = sourceDishes;

                // 1. Normalize Names for Title
                const names = rawDishes.map(d => d.name || d.standard_name || '未命名');

                if (names.length === 0) {
                    title = sourceTitleRaw || title;
                } else if (names.length <= 2) {
                    title = names.join('、');
                } else {
                    title = `${names[0]}等${names.length}个`;
                }

                // 2. Get Summary Details
                if (sourceSummary) {
                    summaryInfo.energy = sourceSummary.totalEnergy || sourceSummary.total_energy_kj || 0;

                    // Get Weight
                    if (window.Dashboard && window.Dashboard.currentDietTotals && window.Dashboard.currentSession === session) {
                        summaryInfo.energy = window.Dashboard.currentDietTotals.totalEnergy || summaryInfo.energy;
                        summaryInfo.weight = window.Dashboard.currentDietTotals.totalWeightG || 0;
                    } else {
                        summaryInfo.weight = rawDishes.reduce((sum, d) => {
                            let w = d.weight_g || d.weight || 0;
                            if (!w && d.ingredients) {
                                w = d.ingredients.reduce((isum, ing) => isum + (ing.weight_g || 0), 0);
                            }
                            return sum + w;
                        }, 0);
                    }
                }
            } else {
                console.warn('[QuickInput] Failed to extract data from session!', session);
            }

            console.log('[QuickInput] Summary Info:', summaryInfo, 'Title:', title);

            // Snapshot data for template execution
            const normalizedDishes = rawDishes.map(d => this._normalizeDish(d));
            console.log('[QuickInput] Normalized Dishes snapshot:', normalizedDishes);

            const templateData = {
                dishes: normalizedDishes
            };

            const newTemplate = {
                id: session.id,
                title: title,
                summary: summaryInfo,
                templateData: templateData,
                addedAt: Date.now()
            };

            API.saveDietTemplate(newTemplate).then(() => {
                this.templates.unshift(newTemplate);
                if (window.ToastUtils) ToastUtils.show('已收藏为快捷模板', 'success');
                if (window.SidebarModule) window.SidebarModule.refreshFavorites();
                if (window.Dashboard) window.Dashboard.renderResult(session);
            }).catch(e => {
                console.error("Save failed", e);
                if (window.ToastUtils) ToastUtils.show("保存失败", "error");
            });
        }

        // Refresh UI
        if (window.SidebarModule && window.SidebarModule.refreshFavorites) {
            window.SidebarModule.refreshFavorites();
        }

        // Force Re-render to update Star icon status
        if (window.Dashboard) window.Dashboard.renderResult(session);
    },

    renameFavorite(favId, newTitle) {
        API.updateDietTemplate(favId, { title: newTitle }).then(() => {
            const index = this.templates.findIndex(f => f.id === favId);
            if (index !== -1) {
                this.templates[index].title = newTitle;
                if (window.SidebarModule) window.SidebarModule.refreshFavorites();
                if (window.ToastUtils) ToastUtils.show('重命名成功', 'success');
            }
        }).catch(e => {
            console.error("Rename failed", e);
            if (window.ToastUtils) ToastUtils.show("重命名失败", "error");
        });
    },

    markProtein(session) {
        // Placeholder for Protein Efficiency Logic
        const price = prompt("请输入本餐大致金额 (用于计算蛋白性价比):", "0");
        if (price !== null) {
            if (window.ToastUtils) ToastUtils.show(`已标记金额: ${price}`, 'success');
            // Save logic here...
        }
    },


    // ================= Execution Logic =================

    /**
     * Execute a Favorite Card as a Template
     */
    async executeFavorite(favId) {
        console.log('[QuickInput] executeFavorite called with ID:', favId);
        if (!window.Dashboard) return;
        const d = window.Dashboard;

        if (d.checkDemoLimit && d.checkDemoLimit()) return;

        // 1. Try to find in local favorites first
        const favorites = this.getFavorites();
        const localFav = favorites.find(f => f.id === favId);
        console.log('[QuickInput] Found localFav:', localFav);

        let templateData = null;
        let sourceTitle = '';

        if (localFav && localFav.templateData) {
            // Use local cached data
            templateData = localFav.templateData;
            sourceTitle = localFav.title;
            // CHECK LOG: Is templateData valid?
            console.log('[QuickInput] Using local templateData:', templateData);
        } else {
            // Fallback: Fetch from API if it was a real card ID
            console.log('[QuickInput] Fallback to API fetch for ID:', favId);
            try {
                d.showLoading(true);
                const card = await API.getCard(favId);
                if (card) {
                    sourceTitle = card.user_title || card.title;
                    const ver = card.versions[card.versions.length - 1];
                    if (ver && ver.raw_result && ver.raw_result.dishes) {
                        templateData = { dishes: ver.raw_result.dishes };
                    }
                }
            } catch (e) {
                console.warn("Failed to load generic card", e);
            }
        }

        if (!templateData || !templateData.dishes) {
            d.updateStatus('');
            if (window.ToastUtils) ToastUtils.show("模板数据丢失", "error");
            return;
        }

        // 2. Prepare new session data
        const parsedDishes = templateData.dishes.map(dish => {
            const newDish = this._normalizeDish(JSON.parse(JSON.stringify(dish)));
            if (newDish.id) delete newDish.id;

            // Ensure ingredients are locked (proportional scale)
            if (newDish.ingredients) {
                newDish.ingredients.forEach(ing => {
                    ing._proportionalScale = true;
                    // Calculate density for proportional scaling
                    const w = Number(ing.weight_g) || 0;
                    if (w > 0 && ing.macros) {
                        ing._density = {
                            protein_per_g: (Number(ing.macros.protein_g) || 0) / w,
                            fat_per_g: (Number(ing.macros.fat_g) || 0) / w,
                            carbs_per_g: (Number(ing.macros.carbs_g) || 0) / w,
                            fiber_per_g: (Number(ing.macros.fiber_g) || 0) / w,
                            sodium_per_g: (Number(ing.macros.sodium_mg) || 0) / w,
                            energy_per_g: (Number(ing.energy_kj) || 0) / w
                        };
                    }
                });
            }
            return newDish;
        });

        // 3. Create Session
        if (!d.currentDialogueId) {
            try {
                const diag = await API.createDialogue("快捷记录");
                d.currentDialogueId = diag.id;
            } catch (e) { /* ignore */ }
        }

        const session = d.createSession('', []);
        session.dialogueId = d.currentDialogueId;
        session.persistentCardId = window.DateFormatter ? window.DateFormatter.generateId('card') : `card-${Date.now()}`;
        session.isQuickRecord = true; // Mark as Quick Record session
        d.currentSession = session;

        // 4. Construct Data
        const initialData = {
            type: 'diet',
            title: sourceTitle || '快捷记录',
            summary: {
                mealName: sourceTitle || '快捷记录',
                dietTime: this.guessDietTime(),
                totalEnergy: 0, totalProtein: 0, totalCarbs: 0, totalFat: 0,
            },
            dishes: parsedDishes,
            advice: '',
            capturedLabels: [],
            context: {
                today_so_far: {
                    consumed_energy_kj: 0,
                    consumed_protein_g: 0,
                    consumed_fat_g: 0,
                    consumed_carbs_g: 0,
                    consumed_sodium_mg: 0,
                    consumed_fiber_g: 0
                },
                user_target: window.Dashboard.currentUserTarget || {}
            }
        };

        // 5. Version
        session.versions.push({
            number: 1,
            createdAt: new Date(),
            userNote: '',
            rawResult: {
                dishes: parsedDishes,
                context: initialData.context
            },
            parsedData: initialData,
            advice: '',
            adviceLoading: false,
            isDraft: true
        });
        session.currentVersion = 1;

        // 6. Force Expand AI Dishes
        if (!d.dietIngredientsCollapsed) d.dietIngredientsCollapsed = {};
        parsedDishes.forEach((dishItem, idx) => {
            if (!dishItem.id) dishItem.id = Date.now() + idx;
            if (dishItem.source === 'ai') {
                d.dietIngredientsCollapsed[dishItem.id] = false;
            }
        });

        // 7. Render
        d.updateStatus('');
        d.renderResult(session);

        // 8. Fetch Today's Summary
        if (API.getTodaySummary) {
            API.getTodaySummary().then(resp => {
                if (resp.success && resp.summary) {
                    // Update context
                    initialData.context.today_so_far = resp.summary;
                    // Sync to rawResult for persistence
                    session.versions[0].rawResult.context = initialData.context;
                    if (d.currentSession === session) {
                        d.renderResult(session);

                        setTimeout(() => {
                            const firstInput = document.querySelector('.js-ing-field[data-field="weight_g"], .cell-input[oninput*="weight"]');
                            if (firstInput) firstInput.focus();
                        }, 50);
                    }
                }
            }).catch(e => console.warn('[QuickInput] Failed to fetch summary', e));
        }

        // 9. Restore Input Focus (Immediate)
        setTimeout(() => {
            const firstInput = document.querySelector('.js-ing-field[data-field="weight_g"], .cell-input[oninput*="weight"]');
            if (firstInput) firstInput.focus();
        }, 100);
    },

    /**
     * Helper to normalize dish structure
     * Ensures 'name' exists (fallback to standard_name)
     * Ensures 'source' is set
     */
    _normalizeDish(dish) {
        // Deep clone first if not already? Assumes input is mutable or clone.
        // We just modify it.
        if (!dish.name && dish.standard_name) {
            dish.name = dish.standard_name;
        }
        if (!dish.name) dish.name = '未命名菜式';

        if (!dish.source) {
            dish.source = (dish.ingredients && dish.ingredients.length > 0) ? 'ai' : 'user';
        }
        return dish;
    },

    // Legacy function for hardcoded template
    applyTemplate(template) {
        this._applyLegacyTemplate(template);
    },

    _applyLegacyTemplate(template) {
        if (!window.Dashboard) return;
        const d = window.Dashboard;
        // 1. Create Session
        const session = d.createSession('', []);
        session.dialogueId = d.currentDialogueId;
        session.persistentCardId = window.DateFormatter ? window.DateFormatter.generateId('card') : `card-${Date.now()}`;
        d.currentSession = session;

        // 2. Build Ingredients with Density for Auto-Calc
        const dishId = Date.now();
        const ingredients = template.ingredients.map((item, idx) => {
            const p = item.per_100g;
            const density = {
                protein_per_g: p.protein / 100,
                fat_per_g: p.fat / 100,
                carbs_per_g: p.carbs / 100,
                fiber_per_g: p.fiber / 100,
                sodium_per_g: p.sodium / 100
            };

            return {
                name_zh: item.name,
                weight_g: 0, // Start empty
                macros: { protein_g: 0, fat_g: 0, carbs_g: 0, fiber_g: 0, sodium_mg: 0 },
                _density: density,
                _proportionalScale: true
            };
        });

        // 3. Initialize Data
        const initialData = {
            type: 'diet',
            title: template.name,
            summary: {
                mealName: template.name,
                totalEnergy: 0, totalProtein: 0, totalCarbs: 0, totalFat: 0,
                dietTime: this.guessDietTime()
            },
            dishes: [
                {
                    id: dishId,
                    source: 'ai',
                    name: template.name,
                    ingredients: ingredients
                }
            ],
            advice: ''
        };

        // 4. Create Version
        session.versions.push({
            number: 1,
            createdAt: new Date(),
            userNote: '',
            rawResult: {},
            parsedData: initialData,
            advice: '',
            adviceLoading: false,
            isDraft: true
        });
        session.currentVersion = 1;

        if (!d.dietIngredientsCollapsed) d.dietIngredientsCollapsed = {};
        d.dietIngredientsCollapsed[dishId] = false;

        d.renderResult(session);
        setTimeout(() => {
            const firstInput = document.querySelector('.js-ing-field[data-field="weight_g"]');
            if (firstInput) firstInput.focus();
        }, 100);
    },

    guessDietTime() {
        const hour = new Date().getHours();
        if (hour >= 5 && hour < 10) return 'breakfast';
        if (hour >= 10 && hour < 14) return 'lunch';
        if (hour >= 14 && hour < 17) return 'snack';
        if (hour >= 17 && hour < 21) return 'dinner';
        return 'snack';
    }
};

window.QuickInputModule = QuickInputModule;
