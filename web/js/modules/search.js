/**
 * Search Module
 *
 * Provides a reusable SearchController for Global Search (Sidebar) and Inline Search (Add Dish).
 * Unified logic:
 * 1. Empty Input -> Show Recent History
 * 2. Typed Input -> Search Products + History
 * 3. Standardized Rendering & Interaction
 */

class SearchController {
    constructor(options) {
        this.input = options.input;
        this.resultsPanel = options.resultsPanel; // Can be a shared container or specific
        this.onSelect = options.onSelect || (() => { });
        this.mode = options.mode || 'global'; // 'global' or 'dish'
        this.debounceWait = options.debounceWait || 300;

        // State
        this.debouncedSearch = this.debounce(this.handleSearch.bind(this), this.debounceWait);
        this.selectedIndex = -1;
        this.lastQuery = '';

        this.bindEvents();
    }

    bindEvents() {
        if (!this.input) return;

        this.input.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            this.debouncedSearch(query);
        });

        this.input.addEventListener('focus', () => {
            // Trigger search immediately on focus (supports empty for recents)
            const query = this.input.value.trim();
            this.handleSearch(query);
        });

        if (this.useEditableUI()) {
            this.input.addEventListener('keydown', (e) => this.onKeyDown(e));
            this.input.addEventListener('focusout', () => {
                setTimeout(() => {
                    if (!this.resultsPanel.contains(document.activeElement) &&
                        document.activeElement !== this.input) {
                        this.hide();
                    }
                }, 100);
            });
        } else {
            // Hide logic: Click outside
            document.addEventListener('click', (e) => {
                if (this.isVisible() &&
                    !this.input.contains(e.target) &&
                    !this.resultsPanel.contains(e.target)) {
                    this.hide();
                }
            });
        }
    }

    debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    async handleSearch(query) {
        this.lastQuery = query;
        if (typeof Auth !== 'undefined' && Auth.isDemoMode && Auth.isDemoMode()) {
            if (this.resultsPanel) {
                this.resultsPanel.innerHTML = '';
                this.hide();
            }
            return;
        }
        // Mode 1: Empty Query
        if (query.length === 0) {
            console.log('test-searchmode-empty', this.mode)
            if (this.mode === 'dish') {
                try {
                    const results = await window.API.searchFood('');
                    this.renderDishResults(results, '');
                } catch (err) {
                    console.error('[Search] Failed:', err);
                    this.renderError();
                }
                return;
            }
            if (this.mode === 'product') {
                try {
                    const results = await window.API.searchFood('');
                    const products = results.filter(r => r.type === 'product');
                    this.renderDishResults(products, '');
                } catch (err) {
                    this.renderError();
                }
                return;
            }
            await this.loadRecents();
            return;
        }

        // Mode 2: Search Query
        try {
            console.log('test-searchmode', this.mode, query)
            if (this.mode === 'dish') {
                console.log('test-searchfood', query)
                const results = await window.API.searchFood(query);
                this.renderDishResults(results, query);
                return;
            }
            if (this.mode === 'product') {
                const results = await window.API.searchFood(query);
                const products = results.filter(r => r.type === 'product');
                this.renderDishResults(products, query);
                return;
            }

            console.log('test-searchglobal', query)
            const data = await window.API.searchGlobal(query);

            this.render(data, false);
        } catch (err) {
            console.error('[Search] Failed:', err);
            this.renderError();
        }
    }

    async loadRecents() {
        try {
            if (this.mode === 'global') {
                // Unified API call for Global Empty State
                const data = await window.API.searchGlobal('');
                console.log('test-searchGlobal-empty', data);

                // Ensure data structure safety
                const safeData = {
                    cards: data.cards || [],
                    products: data.products || [],
                    dialogues: data.dialogues || []
                };

                this.render(safeData, true);
                return;
            }

            // Dish mode: Keep legacy behavior (only cards) or unify if API supports
            let cards = await window.API.getRecentCards();
            cards = this.filterDietCards(cards);

            const data = {
                cards: cards || [],
                products: [],
                dialogues: []
            };

            this.render(data, true);
        } catch (e) {
            console.warn('[Search] Load recents failed', e);
        }
    }

    render(data, isRecent = false) {
        if (!this.resultsPanel) return;

        let { products, cards, dialogues } = data || {};
        let filteredCards = this.filterDietCards(cards);
        let filteredProducts = Array.isArray(products) ? products : [];
        let filteredDialogues = Array.isArray(dialogues) ? dialogues : [];
        let emptyDishCards = [];

        // Logic for Default/Empty Input:
        // Selection: Top 3 Products -> Dishes -> Remaining Products (Total 5)
        // Grouping: All Products -> All Dishes -> Dialogues
        if (this.mode === 'global' && !this.lastQuery) {
            const limited = this.limitEmptyGlobalResults(filteredProducts, filteredCards);
            filteredProducts = limited.products;
            emptyDishCards = limited.dishCards; // Selected dishes for display
            filteredCards = []; // Clear standard cards list to avoid dupes/wrong order
            filteredDialogues = [];
        }
        let html = '';

        const hasResults = (filteredProducts?.length > 0)
            || (filteredCards?.length > 0)
            || (emptyDishCards?.length > 0)
            || (filteredDialogues?.length > 0);

        if (!hasResults) {
            if (isRecent) {
                html = '<div class="search-empty-hint">输入关键词搜索...</div>';
            } else {
                html = '<div class="search-empty">无匹配结果</div>';
            }
            this.resultsPanel.innerHTML = html;
            if (isRecent && !html) this.hide();
            else this.show();
            return;
        }

        // 1. Group: Products
        if (filteredProducts && filteredProducts.length > 0) {
            html += `<div class="search-section-title">产品</div>`;
            filteredProducts.forEach(p => {
                const name = p.product_name || p.name || '未命名产品';
                const brand = p.brand || '';
                const variant = p.variant || '';
                const extra = [brand, variant].filter(Boolean).join(' · ');
                const itemData = { type: 'product', data: p };
                const pStr = this.encodeItem(itemData);
                const title = this.lastQuery ? this.highlightMatch(name, this.lastQuery) : this.escapeHtml(name);

                const metaHtml = this.lastQuery ? this.highlightMatch(extra, this.lastQuery) : this.escapeHtml(extra);

                html += `
                    <div class="search-result-item js-search-item" data-item="${pStr}">
                        <div class="search-icon">🥗</div>
                        <div class="search-content">
                            <div class="search-title">${title}</div>
                            <div class="search-meta">${metaHtml}</div>
                        </div>
                    </div>
                `;
            });
        }

        const allDishCards = [...emptyDishCards, ...filteredCards];

        if (allDishCards.length > 0) {
            html += `<div class="search-section-title">菜式</div>`;
            allDishCards.forEach(c => {
                const info = this.buildCardDisplay(c);
                const itemData = { type: 'card', data: c };
                const cStr = this.encodeItem(itemData);
                const title = this.lastQuery ? this.highlightMatch(info.title, this.lastQuery) : this.escapeHtml(info.title);

                html += `
                    <div class="search-result-item js-search-item" data-item="${cStr}">
                        <div class="search-icon">🥣</div>
                        <div class="search-content">
                            <div class="search-title">${title}</div>
                            <div class="search-meta">${this.escapeHtml(info.meta)}</div>
                        </div>
                    </div>
                `;
            });
        }

        // 4. Group: Dialogues
        if (this.mode === 'global' && filteredDialogues && filteredDialogues.length > 0) {
            html += `<div class="search-section-title">对话</div>`;
            filteredDialogues.forEach(d => {
                const title = d.title || '未命名对话';
                const date = window.DateFormatter?.formatSmart
                    ? window.DateFormatter.formatSmart(d.updated_at)
                    : this.formatTime(d.updated_at);
                const itemData = { type: 'dialogue', id: d.id };
                const dStr = this.encodeItem(itemData);
                const titleHtml = this.lastQuery ? this.highlightMatch(title, this.lastQuery) : this.escapeHtml(title);

                html += `
                    <div class="search-result-item js-search-item" data-item="${dStr}">
                        <div class="search-icon">💬</div>
                        <div class="search-content">
                            <div class="search-title">${titleHtml}</div>
                            <div class="search-meta">${date}</div>
                        </div>
                    </div>
                `;
            });
        }

        this.resultsPanel.innerHTML = html;
        this.selectedIndex = -1;
        this.bindResultClicks();
        this.show();
    }

    renderDishResults(results, query) {
        if (!this.resultsPanel) return;

        const items = Array.isArray(results) ? results : [];
        let products = items.filter(i => i.type === 'product');
        let dishes = items.filter(i => i.type === 'dish');
        const hasQuery = Boolean(query);

        if (!hasQuery) {
            products = products.slice(0, 5);
            dishes = dishes.slice(0, 5);
        }

        if (products.length === 0 && dishes.length === 0) {
            this.resultsPanel.innerHTML = '<div class="editable-name-suggestion">无匹配结果</div>';
            this.show();
            return;
        }

        let html = '';

        if (products.length > 0) {
            html += `<div class="search-section-title">产品</div>`;
            products.forEach(p => {
                const data = p.data || {};
                const name = data.product_name || data.name || '未命名产品';
                const brand = data.brand || '';
                const variant = data.variant || '';
                const extra = [brand, variant].filter(Boolean).join(' · ');
                const pStr = this.encodeItem(p);
                const title = hasQuery ? this.highlightMatch(name, query) : this.escapeHtml(name);

                const metaHtml = hasQuery ? this.highlightMatch(extra, query) : this.escapeHtml(extra);
                html += `
                    <div class="editable-name-suggestion js-search-item" data-item="${pStr}">
                        🥗 ${title}
                        <span style="float:right; color:#999;">${metaHtml}</span>
                    </div>
                `;
            });
        }

        if (dishes.length > 0) {
            html += `<div class="search-section-title">菜式</div>`;
            dishes.forEach(d => {
                const data = d.data || {};
                const name = data.dish_name || '未命名菜式';
                const macros = data.macros_per_100g || {};
                const avgWeight = Number(data.recorded_weight_g) || 0;
                const energyKj100 = this.calcEnergyKJ(macros);
                const totalEnergyKj = avgWeight > 0 ? (energyKj100 * avgWeight / 100) : 0;
                const dStr = this.encodeItem(d);
                const title = hasQuery ? this.highlightMatch(name, query) : this.escapeHtml(name);

                html += `
                    <div class="editable-name-suggestion js-search-item" data-item="${dStr}">
                        <div class="dish-suggest-row">
                            <span class="dish-suggest-title">🥣 ${title}</span>
                            <span class="dish-suggest-meta">${this.formatEnergy(totalEnergyKj)} · ${avgWeight}g</span>
                        </div>
                    </div>
                `;
            });
        }

        this.resultsPanel.innerHTML = html;
        this.selectedIndex = -1;
        this.bindResultClicks();
        this.show();
    }

    renderError() {
        if (!this.resultsPanel) return;
        this.resultsPanel.innerHTML = '<div class="search-empty">搜索服务暂不可用</div>';
        this.show();
    }

    show() {
        if (this.useEditableUI()) this.resultsPanel.classList.add('visible');
        else this.resultsPanel.classList.remove('hidden');
    }
    hide() {
        if (this.useEditableUI()) this.resultsPanel.classList.remove('visible');
        else this.resultsPanel.classList.add('hidden');
    }
    isVisible() {
        return this.useEditableUI()
            ? this.resultsPanel.classList.contains('visible')
            : !this.resultsPanel.classList.contains('hidden');
    }

    escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    filterDietCards(cards) {
        if (!Array.isArray(cards)) return [];
        return cards.filter(c => {
            const mode = c?.mode;
            return !mode || mode === 'diet';
        });
    }

    limitEmptyGlobalResults(products, cards) {
        let pList = Array.isArray(products) ? products.slice() : [];
        let cList = Array.isArray(cards) ? cards.slice() : [];

        const MAX_TOTAL = 5;
        let currentCount = 0;

        const outProducts = [];
        const outDishCards = [];

        // 1. Take up to 3 products
        while (outProducts.length < 3 && pList.length > 0) {
            outProducts.push(pList.shift());
            currentCount++;
        }

        // 2. Take dishes until MAX_TOTAL (fill mechanism)
        // User Logic: "产品先填3个...然后菜式填入...然后再按照顺序填充(产品)"
        // This implies priority: Top 3 Products > Dishes > Remaining Products
        while (currentCount < MAX_TOTAL && cList.length > 0) {
            outDishCards.push(cList.shift());
            currentCount++;
        }

        // 3. Fill remaining limit with remaining Products
        while (currentCount < MAX_TOTAL && pList.length > 0) {
            outProducts.push(pList.shift());
            currentCount++;
        }

        return { products: outProducts, dishCards: outDishCards };
    }

    getMealTimeLabel(value) {
        const v = String(value || '').toLowerCase();
        const map = {
            breakfast: '早餐',
            lunch: '午餐',
            dinner: '晚餐',
            snack: '加餐'
        };
        if (!v) return '';
        return map[v] || value;
    }

    formatTime(value) {
        if (!value) return '';
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) return '';
        const hh = String(dt.getHours()).padStart(2, '0');
        const mm = String(dt.getMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    }

    buildCardDisplay(card) {
        let mealTime = '';
        let dishCount = 0;
        let firstDishName = '';
        let mealName = '';
        let energyKj = 0;
        let weightG = 0;
        let occurredAt = card?.occurred_at || card?.created_at || card?.updated_at;

        if (card?.versions && card.versions.length > 0) {
            const idx = Math.max(0, (card.current_version || card.versions.length) - 1);
            const latest = card.versions[idx] || card.versions[card.versions.length - 1];
            const raw = latest?.raw_result || {};
            const summary = raw.meal_summary || {};
            mealTime = summary.diet_time || summary.diet_time_label || '';
            mealName = summary.meal_name || '';
            energyKj = Number(summary.total_energy_kj || 0);
            weightG = Number(summary.total_weight_g || summary.total_weight || 0);

            const dishes = Array.isArray(raw.dishes) ? raw.dishes : [];
            const names = dishes.map(d => d.standard_name || d.name).filter(Boolean);
            dishCount = names.length;
            firstDishName = names[0] || '';
        } else {
            mealTime = card?.diet_time || '';
            mealName = card?.meal_name || card?.user_title || '';
            energyKj = Number(card?.total_energy_kj || card?.energy_kj || 0);
            weightG = Number(card?.total_weight_g || card?.total_weight || 0);
            dishCount = Number(card?.dish_count || (card?.dish_names ? card.dish_names.length : 0));
            firstDishName = card?.first_dish_name || (card?.dish_names ? card.dish_names[0] : '');
        }

        const mealLabel = this.getMealTimeLabel(mealTime);
        const titleName = firstDishName || mealName || '未命名餐食';
        const titleCount = dishCount > 1 ? `等${dishCount}个` : '';
        const title = `${mealLabel ? mealLabel + ' ' : ''}${titleName}${titleCount}`;

        const timeText = window.DateFormatter?.formatSmart
            ? DateFormatter.formatSmart(occurredAt)
            : this.formatTime(occurredAt);
        const energyText = energyKj > 0 ? `${Math.round(energyKj)}kJ` : '';
        const weightText = weightG > 0 ? `${Math.round(weightG)}g` : '';
        const metaParts = [timeText, energyText, weightText].filter(Boolean);

        return {
            title,
            meta: metaParts.join(' · ') || '—'
        };
    }

    buildDishCardDisplay(card) {
        let mealTime = '';
        let energyKj = 0;
        let weightG = 0;
        let firstDishName = '';
        let mealName = '';
        let occurredAt = card?.occurred_at || card?.created_at || card?.updated_at;

        if (card?.versions && card.versions.length > 0) {
            const idx = Math.max(0, (card.current_version || card.versions.length) - 1);
            const latest = card.versions[idx] || card.versions[card.versions.length - 1];
            const raw = latest?.raw_result || {};
            const summary = raw.meal_summary || {};
            mealTime = summary.diet_time || summary.diet_time_label || '';
            mealName = summary.meal_name || '';
            energyKj = Number(summary.total_energy_kj || 0);
            weightG = Number(summary.total_weight_g || summary.total_weight || 0);

            const dishes = Array.isArray(raw.dishes) ? raw.dishes : [];
            const names = dishes.map(d => d.standard_name || d.name).filter(Boolean);
            firstDishName = names[0] || '';
        } else {
            mealTime = card?.diet_time || '';
            mealName = card?.meal_name || card?.user_title || '';
            energyKj = Number(card?.total_energy_kj || card?.energy_kj || 0);
            weightG = Number(card?.total_weight_g || card?.total_weight || 0);
            firstDishName = card?.first_dish_name || (card?.dish_names ? card.dish_names[0] : '');
        }

        const mealLabel = this.getMealTimeLabel(mealTime);
        const title = firstDishName || mealName || '未命名菜式';

        const timeText = window.DateFormatter?.formatSmart
            ? DateFormatter.formatSmart(occurredAt)
            : this.formatTime(occurredAt);
        const energyText = energyKj > 0 ? `${Math.round(energyKj)}kJ` : '';
        const weightText = weightG > 0 ? `${Math.round(weightG)}g` : '';
        const metaParts = [mealLabel, timeText, energyText, weightText].filter(Boolean);

        return {
            title,
            meta: metaParts.join(' · ') || '—'
        };
    }

    static applyAddDishSelection(dietModule, index, item) {
        if (!dietModule || !dietModule.currentDishes) return false;
        if (!item || (item.type !== 'product' && item.type !== 'dish')) return false;

        const dishIndex = parseInt(index);
        if (!dietModule.currentDishes[dishIndex]) return false;

        const dish = dietModule.currentDishes[dishIndex];
        const data = item.data || {};

        const weightFromRow = Number(dish.weight);
        const useWeight = item.type === 'product'
            ? (weightFromRow > 0 ? weightFromRow : 100)
            : (Number(data.recorded_weight_g) || 0);

        const macros = SearchController.extractMacrosPer100g(data);

        const energyKj100 = parseFloat(macros.energy_kj || 0);
        const p100 = parseFloat(macros.protein_g || 0);
        const f100 = parseFloat(macros.fat_g || 0);
        const c100 = parseFloat(macros.carbs_g || 0);
        const fib100 = parseFloat(macros.fiber_g || 0);
        const na100 = parseFloat(macros.sodium_mg || 0);

        const ratio = useWeight > 0 ? (useWeight / 100) : 0;
        const r1 = (v) => Math.round((Number(v) || 0) * 10) / 10;
        const r0 = (v) => Math.round(Number(v) || 0);

        const name = item.type === 'product'
            ? (data.product_name || data.name || '未命名产品')
            : (data.dish_name || '未命名菜式');

        dish.name = name;
        if (dish.standard_name) dish.standard_name = name;

        dish.weight = r1(useWeight);
        dish.protein = r1(p100 * ratio);
        dish.fat = r1(f100 * ratio);
        dish.carb = r1(c100 * ratio);
        dish.fiber = r1(fib100 * ratio);
        dish.sodium_mg = r0(na100 * ratio);
        dish.energy_kj = r0(energyKj100 * ratio);
        dish._energyPer100g = energyKj100;
        dish.source = 'user';
        dish.ingredients = [];

        return true;
    }

    static parseServingWeightG(tableUnitStr, density) {
        const servingStr = String(tableUnitStr || '100g').toLowerCase();
        const match = servingStr.match(/([\d.]+)/);
        let servingNumeric = match ? parseFloat(match[1]) : 100;
        if (!servingNumeric || isNaN(servingNumeric)) servingNumeric = 100;
        const factor = Number(density) || 1.0;
        return servingNumeric * factor;
    }

    static extractMacrosPer100g(data) {
        if (data.macros_per_100g) return data.macros_per_100g;

        const getVal = (obj, keys) => {
            for (const k of keys) {
                if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return parseFloat(obj[k]);
            }
            return 0;
        };

        // Strict priority: Explicit 100g flat keys OR Serving calculation
        let p, f, c, fib, na, scaleTo100g = 1;

        // Serving Mode
        const density = Number(data.density_factor) || Number(data.density) || 1.0;
        const servingAmount = Number(data.table_amount) || 0;
        const servingWeightG = servingAmount > 0
            ? (servingAmount * density)
            : SearchController.parseServingWeightG(data.table_unit, density);

        scaleTo100g = servingWeightG > 0 ? (100 / servingWeightG) : 1;

        p = getVal(data, ['protein_g_per_serving']);
        f = getVal(data, ['fat_g_per_serving']);
        c = getVal(data, ['carbs_g_per_serving']);
        fib = getVal(data, ['fiber_g_per_serving']);
        na = getVal(data, ['sodium_mg_per_serving']);

        return {
            protein_g: p * scaleTo100g,
            fat_g: f * scaleTo100g,
            carbs_g: c * scaleTo100g,
            fiber_g: fib * scaleTo100g,
            sodium_mg: na * scaleTo100g
        };
    }

    static extractEnergyPer100g(data, macros) {
        // 1. Explicit 100g key (Priority 1)
        console.log('test-extractEnergyPer100g', data);

        // 2. Serving calculation
        const density = Number(data.density_factor) || 1.0;
        const servingAmount = Number(data.table_amount) || 0;

        // Calculate Serving Weight
        const servingWeightG = servingAmount * density;

        // Check for Serving Energy Value
        let energyKjServing = Number(data.energy_kj_per_serving) || 0;

        if (energyKjServing > 0 && servingWeightG > 0) {
            return energyKjServing * (100 / servingWeightG);
        }

        // Fallback to macro-based calculation
        const useMacros = macros || SearchController.extractMacrosPer100g(data);
        console.log('test-extractEnergyPer100g-useMacros', useMacros);
        return SearchController.calcEnergyKJ(useMacros);
    }

    calcEnergyKJ(macros) {
        const p = parseFloat(macros.protein_g || 0);
        const f = parseFloat(macros.fat_g || 0);
        const c = parseFloat(macros.carbs_g || 0);
        const kcal = (p * 4) + (f * 9) + (c * 4);
        return kcal * 4.184;
    }

    formatEnergy(valueKj) {
        const val = Number(valueKj) || 0;
        return `${Math.round(val)}kJ`;
    }

    highlightMatch(text, query) {
        if (!query) return this.escapeHtml(text);
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return this.escapeHtml(text);
        const before = text.slice(0, idx);
        const match = text.slice(idx, idx + query.length);
        const after = text.slice(idx + query.length);
        return `${this.escapeHtml(before)}<strong>${this.escapeHtml(match)}</strong>${this.escapeHtml(after)}`;
    }

    encodeItem(item) {
        return encodeURIComponent(JSON.stringify(item));
    }

    bindResultClicks() {
        if (!this.resultsPanel) return;
        const items = this.resultsPanel.querySelectorAll('.js-search-item');
        items.forEach(el => {
            el.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const itemStr = el.dataset.item;
                SearchController.handleSelect(this.id, itemStr);
            });
        });
    }

    useEditableUI() {
        return this.resultsPanel?.classList.contains('editable-name-suggestions');
    }

    onKeyDown(e) {
        const items = this.resultsPanel.querySelectorAll('.editable-name-suggestion');
        if (!items || items.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
            this.updateSelection(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
            this.updateSelection(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (this.selectedIndex >= 0 && items[this.selectedIndex]) {
                const itemStr = items[this.selectedIndex].dataset.item;
                if (itemStr) {
                    SearchController.handleSelect(this.id, itemStr);
                } else {
                    items[this.selectedIndex].click();
                }
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this.hide();
        }
    }

    updateSelection(items) {
        items.forEach((el, i) => {
            if (i === this.selectedIndex) {
                el.classList.add('selected');
                el.scrollIntoView({ block: 'nearest' });
            } else {
                el.classList.remove('selected');
            }
        });
    }

    // Static registry to handle onclick callbacks from HTML string
    static instances = {};
    static register(instance) {
        const id = 'search_' + Math.random().toString(36).substr(2, 9);
        instance.id = id;
        this.instances[id] = instance;
        return id;
    }

    static handleSelect(instanceId, itemStr) {
        const instance = this.instances[instanceId];
        if (instance && instance.onSelect) {
            try {
                const item = JSON.parse(decodeURIComponent(itemStr));
                instance.onSelect(item);
                instance.hide();
                if (instance.mode === 'dish' && instance.input) {
                    const data = item.data || {};
                    const name = item.type === 'product'
                        ? (data.product_name || data.name || '')
                        : (data.dish_name || '');
                    instance.input.value = name;
                } else if (instance.input) {
                    instance.input.value = '';
                    instance.input.blur();
                }
            } catch (e) {
                console.error('[Search] Select error', e);
            }
        }
    }
}

// Singleton Wrapper for Legacy Global Search (Sidebar)
const GlobalSearchManager = {
    controller: null,

    init() {
        const input = document.getElementById('global-search-input');
        const panel = document.getElementById('global-search-results');

        if (!input || !panel) return;
        this.controller = new SearchController({
            input,
            resultsPanel: panel,
            mode: 'global',
            onSelect: this.handleSelect.bind(this)
        });

        SearchController.register(this.controller);
    },

    async handleSelect(item) {
        console.log('[GlobalSearch] Selected:', item);

        if (item.type === 'product') {
            if (window.Dashboard && window.Dashboard.createRecordFromProduct) {
                await window.Dashboard.createRecordFromProduct(item.data);
            }
        } else if (item.type === 'card') {
            if (window.Dashboard && window.Dashboard.createRecordFromHistory) {
                await window.Dashboard.createRecordFromHistory(item.data.id);
            }
        } else if (item.type === 'dialogue') {
            if (window.Dashboard && window.Dashboard.loadDialogue) {
                window.Dashboard.loadDialogue(item.id);
            }
        }
    },

    // Bridge legacy calls if any
    onProductClick(str) { /* No-op, managed by Controller now */ }
};

window.SearchController = SearchController;
window.GlobalSearchManager = GlobalSearchManager;

