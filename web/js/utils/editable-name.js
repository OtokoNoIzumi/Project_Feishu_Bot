/**
 * Editable Name Component
 *
 * 可编辑名称组件，支持：
 * 1. 点击显示编辑框
 * 2. 模糊匹配建议（基于 dish_library.jsonl）
 * 3. 键盘上下键导航建议列表
 * 4. 回车确认 / Escape 取消
 *
 * 设计原则：
 * - 所有匹配都在本地进行，不请求后端
 * - 仅在保存时触发一次后端请求
 */

const EditableNameModule = {
    // 当前活动的编辑器状态
    _activeEditor: null,
    _selectedIndex: -1, // 当前高亮的建议索引

    // dish_library 缓存
    _dishLibrary: null,
    _dishLibraryLoaded: false,
    _nameMatchCache: new Map(),
    _nameMatchPromiseCache: new Map(),

    /**
     * 初始化：加载 dish_library 数据
     */
    // Search debounce
    _debouncedSearch: null,

    /**
     * 初始化
     */
    init() {
        this._debouncedSearch = this._debounce(async (query, el) => {
            if (typeof Auth !== 'undefined' && Auth.isDemoMode && Auth.isDemoMode()) {
                el.innerHTML = '';
                el.classList.remove('visible');
                return;
            }
            if (!query) {
                el.innerHTML = '';
                el.classList.remove('visible');
                return;
            }
            try {
                const results = await window.API.searchFood(query);
                // 去重：对产品和菜品分别取名字段，优先顺序为：product_name > dish_name
                const dedupMap = new Map();
                (results || []).forEach(r => {
                    let name = '';
                    if (r.type === 'product') {
                        name = r?.data?.product_name || r?.data?.name;
                    } else if (r.type === 'dish') {
                        name = r?.data?.dish_name;
                    }
                    if (!name) return;
                    if (!dedupMap.has(name)) {
                        dedupMap.set(name, r);
                    }
                });
                this._renderSuggestions(el, Array.from(dedupMap.values()), query);
            } catch (e) { console.error(e); }
        }, 300);
    },

    _debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    },

    /**
     * 渲染可编辑名称 HTML
     * @param {string} name - 当前名称
     * @param {string} type - 类型：'dish' | 'card'
     * @param {number|string} index - 索引或 ID
     * @returns {string} HTML 字符串
     */
    renderEditable(name, type, index) {
        const escapedName = this._escapeHtml(name || '未命名');
        return `
            <span class="editable-name"
                  data-type="${type}"
                  data-index="${index}"
                  onclick="EditableNameModule.startEdit(this, event)">
                <span class="editable-name-text">${escapedName}</span>
                <span class="editable-name-badge">new</span>
                <span class="editable-name-icon">✏️</span>
            </span>
        `;
    },

    /**
     * 开始编辑
     */
    startEdit(element, event) {
        // 阻止事件冒泡
        if (event) {
            event.stopPropagation();
        }

        // 如果点击的是编辑器内部，不做处理
        if (this._activeEditor === element) {
            return;
        }

        // 如果已有编辑器，先关闭
        if (this._activeEditor) {
            this.saveEdit(this._activeEditor);
        }

        const type = element.dataset.type;
        const index = element.dataset.index;
        const textEl = element.querySelector('.editable-name-text');
        const currentName = textEl?.textContent || '';

        // 重置选中索引
        this._selectedIndex = -1;

        // 创建编辑器
        element.innerHTML = `
            <div class="editable-name-editor" onclick="event.stopPropagation()">
                <input type="text"
                       class="editable-name-input"
                       value="${this._escapeHtml(currentName)}"
                       data-type="${type}"
                       data-index="${index}"
                       data-original="${this._escapeHtml(currentName)}"
                       autocomplete="off">
                <div class="editable-name-suggestions"></div>
            </div>
        `;

        const input = element.querySelector('.editable-name-input');
        const suggestionsEl = element.querySelector('.editable-name-suggestions');

        // 聚焦并选中
        input.focus();
        input.select();

        // 绑定事件
        input.addEventListener('input', (e) => this._onInput(e, suggestionsEl));
        input.addEventListener('keydown', (e) => this._onKeyDown(e, element, suggestionsEl));

        // 使用 focusout 替代 blur，并检查焦点是否移出编辑器
        element.addEventListener('focusout', (e) => {
            // 检查新的焦点目标是否仍在编辑器内
            setTimeout(() => {
                const editorEl = element.querySelector('.editable-name-editor');
                if (editorEl && !editorEl.contains(document.activeElement)) {
                    // 焦点移出编辑器，保存并关闭
                    if (this._activeEditor === element) {
                        this.saveEdit(element);
                    }
                }
            }, 100);
        });

        // 点击建议项事件委托
        suggestionsEl.addEventListener('mousedown', (e) => {
            // 使用 mousedown 而不是 click，防止 blur 先触发
            const suggestionEl = e.target.closest('.editable-name-suggestion');
            if (suggestionEl) {
                e.preventDefault(); // 阻止 blur

                const jsonStr = suggestionEl.dataset.json;
                // Full Data update
                if (jsonStr) {
                    try {
                        const item = JSON.parse(decodeURIComponent(jsonStr));
                        const type = element.dataset.type;
                        const idx = element.dataset.index;

                        // Call Dashboard to update structure if it's a dish edit
                        if (type === 'dish' && window.Dashboard && window.Dashboard.updateDishFromSearch) {
                            window.Dashboard.updateDishFromSearch(idx, item);
                            // Close editor implies re-render, effectively removing it
                            this._activeEditor = null;
                            return;
                        }

                        // Fallback: just name
                        const val = suggestionEl.dataset.value;
                        input.value = val;
                        this.saveEdit(element);
                        return;
                    } catch (err) { console.error(err); }
                }

                const value = suggestionEl.dataset.value;
                input.value = value;
                this.saveEdit(element);
            }
        });

        this._activeEditor = element;

        // 立即执行一次匹配（使用当前名称作为查询）
        this._showInitialSuggestions(currentName, suggestionsEl);
    },

    /**
     * 进入编辑模式时立即显示建议
     */
    _showInitialSuggestions(currentName, suggestionsEl) {
        if (!this._debouncedSearch) this.init();
        const query = currentName.trim();
        if (!query) {
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.remove('visible');
            return;
        }
        if (this._debouncedSearch) {
            this._debouncedSearch(query, suggestionsEl);
        }
    },

    /**
     * 输入事件：显示模糊匹配建议
     */
    /**
     * 输入事件：显示模糊匹配建议
     */
    _onInput(e, suggestionsEl) {
        if (!this._debouncedSearch) this.init();
        const query = e.target.value.trim();
        this._selectedIndex = -1; // 重置选中

        if (query.length < 1) {
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.remove('visible');
            return;
        }

        // Call Debounced API Search
        if (this._debouncedSearch) {
            this._debouncedSearch(query, suggestionsEl);
        }
    },

    /**
     * 渲染建议列表
     */
    /**
     * 渲染建议列表
     */
    _renderSuggestions(suggestionsEl, suggestions, query) {
        if (!suggestions || suggestions.length === 0) {
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.remove('visible');
            return;
        }

        suggestionsEl.innerHTML = suggestions.map((s, i) => {
            const data = s.data || {};
            const name = data.dish_name || data.product_name || '';
            const avgWeight = Number(data.recorded_weight_g) || 0;
            const energyKj = this._calcDishEnergyKj(data);
            const extra = avgWeight > 0 ? `${Math.round(energyKj)}kJ · ${avgWeight}g` : '';
            const icon = s.type === 'product' ? '🥗' : '🥣';
            const json = encodeURIComponent(JSON.stringify(s));

            return `
            <div class="editable-name-suggestion${i === this._selectedIndex ? ' selected' : ''}"
                 data-value="${this._escapeHtml(name)}"
                 data-json="${json}"
                 data-index="${i}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span>${icon} ${this._highlightMatch(name, query)}</span>
                    <span style="font-size:0.75em; color:#aaa; margin-left:8px;">${extra}</span>
                </div>
            </div>
            `;
        }).join('');
        suggestionsEl.classList.add('visible');
    },

    _calcDishEnergyKj(data) {
        const macros = data.macros_per_100g || {};
        const p = Number(macros.protein_g) || 0;
        const f = Number(macros.fat_g) || 0;
        const c = Number(macros.carbs_g) || 0;
        const kcal100 = EnergyUtils.macrosToKcal(p, f, c);
        const kj100 = EnergyUtils.kcalToKJ(kcal100);
        const avgWeight = Number(data.recorded_weight_g) || 0;
        if (avgWeight <= 0) return 0;
        return (kj100 * avgWeight) / 100;
    },

    /**
     * 获取匹配的建议（从 dish_library）
     */
    _getMatchingSuggestions(query) {
        const results = [];
        const seen = new Set();

        // 从 dish_library 获取建议
        if (this._dishLibrary && this._dishLibrary.length > 0) {
            this._dishLibrary.forEach(item => {
                const dishName = item.dish_name;
                if (!dishName || seen.has(dishName)) return;

                // 如果没有查询，或者名称包含查询
                if (!query || dishName.toLowerCase().includes(query)) {
                    seen.add(dishName);
                    results.push({
                        name: dishName,
                        source: 'library',
                        weight: item.recorded_weight_g || 0
                    });
                }
            });
        }

        // 按名称排序，优先显示精确匹配
        if (query) {
            results.sort((a, b) => {
                const aStarts = a.name.toLowerCase().startsWith(query);
                const bStarts = b.name.toLowerCase().startsWith(query);
                if (aStarts && !bStarts) return -1;
                if (!aStarts && bStarts) return 1;
                return a.name.localeCompare(b.name);
            });
        }

        return results;
    },

    /**
     * 高亮匹配部分
     */
    _highlightMatch(text, query) {
        if (!query) return this._escapeHtml(text);

        const idx = text.toLowerCase().indexOf(query);
        if (idx === -1) return this._escapeHtml(text);

        const before = text.slice(0, idx);
        const match = text.slice(idx, idx + query.length);
        const after = text.slice(idx + query.length);

        return `${this._escapeHtml(before)}<strong>${this._escapeHtml(match)}</strong>${this._escapeHtml(after)}`;
    },

    /**
     * 键盘事件
     */
    _onKeyDown(e, element, suggestionsEl) {
        const suggestions = suggestionsEl.querySelectorAll('.editable-name-suggestion');
        const hasSuggestions = suggestions.length > 0;

        switch (e.key) {
            case 'ArrowDown':
                if (hasSuggestions) {
                    e.preventDefault();
                    this._selectedIndex = Math.min(this._selectedIndex + 1, suggestions.length - 1);
                    this._updateSelection(suggestions);
                }
                break;

            case 'ArrowUp':
                if (hasSuggestions) {
                    e.preventDefault();
                    this._selectedIndex = Math.max(this._selectedIndex - 1, -1);
                    this._updateSelection(suggestions);
                }
                break;

            case 'Enter':
                e.preventDefault();
                // 如果有选中的建议，使用该建议
                if (this._selectedIndex >= 0 && suggestions[this._selectedIndex]) {
                    const value = suggestions[this._selectedIndex].dataset.value;
                    element.querySelector('.editable-name-input').value = value;
                }
                this.saveEdit(element);
                break;

            case 'Escape':
                e.preventDefault();
                this.cancelEdit();
                break;

            case 'Tab':
                // Tab 键：如果有选中的建议，填充但不关闭
                if (this._selectedIndex >= 0 && suggestions[this._selectedIndex]) {
                    e.preventDefault();
                    const value = suggestions[this._selectedIndex].dataset.value;
                    const input = element.querySelector('.editable-name-input');
                    input.value = value;
                    this._selectedIndex = -1;
                    suggestionsEl.innerHTML = '';
                    suggestionsEl.classList.remove('visible');
                }
                break;
        }
    },

    /**
     * 更新选中状态
     */
    _updateSelection(suggestions) {
        suggestions.forEach((el, i) => {
            if (i === this._selectedIndex) {
                el.classList.add('selected');
                // 确保选中项可见
                el.scrollIntoView({ block: 'nearest' });
            } else {
                el.classList.remove('selected');
            }
        });
    },

    /**
     * 保存编辑
     */
    saveEdit(element) {
        if (!element) return;

        const input = element.querySelector('.editable-name-input');
        if (!input) return;

        const newName = input.value.trim();
        const originalName = input.dataset.original || '';
        const type = input.dataset.type;
        const index = input.dataset.index;

        // 恢复显示状态
        element.innerHTML = `
            <span class="editable-name-text">${this._escapeHtml(newName || originalName)}</span>
            <span class="editable-name-icon">✏️</span>
        `;

        this._activeEditor = null;
        this._selectedIndex = -1;

        // 如果名称有变化，触发保存
        if (newName && newName !== originalName) {
            this._triggerSave(type, index, newName);
        }
    },

    /**
     * 取消编辑
     */
    cancelEdit() {
        if (!this._activeEditor) return;

        const input = this._activeEditor.querySelector('.editable-name-input');
        const originalName = input?.dataset.original || '';

        this._activeEditor.innerHTML = `
            <span class="editable-name-text">${this._escapeHtml(originalName)}</span>
            <span class="editable-name-icon">✏️</span>
        `;

        this._activeEditor = null;
        this._selectedIndex = -1;
    },

    /**
     * 触发保存
     */
    _triggerSave(type, index, newName) {
        if (type === 'dish') {
            // 更新 Dish 名称
            if (window.Dashboard && typeof Dashboard.updateDishName === 'function') {
                Dashboard.updateDishName(parseInt(index), newName);
            }
        } else if (type === 'meal') {
            // 更新 Meal 名称（卡片顶部标题）
            if (window.Dashboard && typeof Dashboard.updateMealName === 'function') {
                Dashboard.updateMealName(newName);
            }
        } else if (type === 'card') {
            // 更新 Card 标题
            if (window.Dashboard && typeof Dashboard.updateCardTitle === 'function') {
                Dashboard.updateCardTitle(index, newName);
            }
        }
    },

    refreshNewBadges(container = document) {
        const elements = container.querySelectorAll('.editable-name[data-type="dish"]');
        elements.forEach(el => this._updateNewBadgeForElement(el));
    },

    _updateNewBadgeForElement(element) {
        const textEl = element.querySelector('.editable-name-text');
        if (!textEl) return;

        const name = (textEl.textContent || '').trim();
        if (!name) {
            this._applyNewBadgeState(element, false);
            return;
        }

        if (typeof Auth !== 'undefined' && Auth.isDemoMode && Auth.isDemoMode()) {
            this._applyNewBadgeState(element, false);
            return;
        }

        const key = this._normalizeName(name);
        if (this._nameMatchCache.has(key)) {
            const hasMatch = this._nameMatchCache.get(key);
            this._applyNewBadgeState(element, !hasMatch);
            return;
        }

        if (this._nameMatchPromiseCache.has(key)) {
            return;
        }

        if (!window.API || !window.API.searchFood) {
            return;
        }

        const promise = window.API.searchFood(name)
            .then(results => {
                const hasMatch = this._hasExactMatch(name, results);
                this._nameMatchCache.set(key, hasMatch);
                this._applyNewBadgeState(element, !hasMatch);
            })
            .catch(() => {
                this._applyNewBadgeState(element, false);
            })
            .finally(() => {
                this._nameMatchPromiseCache.delete(key);
            });

        this._nameMatchPromiseCache.set(key, promise);
    },

    _hasExactMatch(name, results) {
        const key = this._normalizeName(name);
        const list = Array.isArray(results) ? results : [];
        for (const item of list) {
            if (item?.type === 'dish') {
                const dishName = item?.data?.dish_name || '';
                if (this._normalizeName(dishName) === key) return true;
            }
            if (item?.type === 'product') {
                const productName = item?.data?.product_name || item?.data?.name || '';
                if (this._normalizeName(productName) === key) return true;
            }
        }
        return false;
    },

    _normalizeName(value) {
        return String(value || '').trim().toLowerCase();
    },

    _applyNewBadgeState(element, isNew) {
        if (isNew) element.classList.add('is-new');
        else element.classList.remove('is-new');
    },

    _escapeHtml(str) {
        if (!str) return '';
        return str.replace(/[&<>"']/g, (m) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[m]);
    }
};

window.EditableNameModule = EditableNameModule;
