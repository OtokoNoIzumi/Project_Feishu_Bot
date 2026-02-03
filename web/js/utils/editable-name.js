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

    /**
     * 初始化：加载 dish_library 数据
     */
    async init() {
        if (this._dishLibraryLoaded) return;

        try {
            const response = await API.get('/diet/dish-library');
            this._dishLibrary = response || [];
            this._dishLibraryLoaded = true;
            console.log(`[EditableName] Loaded ${this._dishLibrary.length} dishes from library`);
        } catch (e) {
            console.error('[EditableName] Failed to load dish library:', e);
            this._dishLibrary = [];
            this._dishLibraryLoaded = true;
        }
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
        const query = currentName.trim().toLowerCase();

        // 获取匹配建议
        const suggestions = this._getMatchingSuggestions(query);

        if (suggestions.length === 0) {
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.remove('visible');
            return;
        }

        // 渲染建议列表
        this._renderSuggestions(suggestionsEl, suggestions, query);
    },

    /**
     * 输入事件：显示模糊匹配建议
     */
    _onInput(e, suggestionsEl) {
        const query = e.target.value.trim().toLowerCase();
        this._selectedIndex = -1; // 重置选中

        if (query.length < 1) {
            // 空输入时显示所有建议（最多8个）
            const allSuggestions = this._getMatchingSuggestions('');
            if (allSuggestions.length > 0) {
                this._renderSuggestions(suggestionsEl, allSuggestions, '');
            } else {
                suggestionsEl.innerHTML = '';
                suggestionsEl.classList.remove('visible');
            }
            return;
        }

        // 获取本地模板数据进行匹配
        const suggestions = this._getMatchingSuggestions(query);

        if (suggestions.length === 0) {
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.remove('visible');
            return;
        }

        // 渲染建议列表
        this._renderSuggestions(suggestionsEl, suggestions, query);
    },

    /**
     * 渲染建议列表
     */
    _renderSuggestions(suggestionsEl, suggestions, query) {
        suggestionsEl.innerHTML = suggestions.slice(0, 8).map((s, i) => `
            <div class="editable-name-suggestion${i === this._selectedIndex ? ' selected' : ''}" 
                 data-value="${this._escapeHtml(s.name)}"
                 data-index="${i}">
                ${query ? this._highlightMatch(s.name, query) : this._escapeHtml(s.name)}
            </div>
        `).join('');
        suggestionsEl.classList.add('visible');
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
