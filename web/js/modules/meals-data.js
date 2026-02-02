/**
 * Meals Data Module
 * 管理"餐食"标签页：快捷记录管理 & 蛋白效力数据
 * CSS 依赖 css/components/common-cards.css 和 css/modules/meals.css
 */
const MealsDataModule = {
    // State
    isExpanded: false,

    init() {
        this._injectModal();
    },

    render(container) {
        // Icons (SVG)
        const iconLightning = `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>`;
        const iconTarget = `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;

        // 使用通用 UI 组件
        const UI = window.UIComponents || { renderTape: () => '' };

        container.innerHTML = `
            <div class="profile-container">
               
               <!-- Quick Records Section -->
               <div class="profile-section">
                   ${UI.renderTape('50px', 2)}
                   <div class="profile-section-header">
                       <div class="profile-section-icon" style="background:#fffbeb; color:#f59e0b;">${iconLightning}</div>
                       <div>
                           <div class="profile-section-title">快捷饮食记录</div>
                           <div class="profile-section-subtitle">我的常用餐食模板</div>
                       </div>
                   </div>
                   
                   <div style="font-size:0.85rem; color:#666; margin-bottom:16px; padding-left:4px;">
                       在分析结果卡片中点击 <span style="color:#f59e0b">⭐</span> 即可收藏到此处。
                   </div>
                   
                   <div id="meals-quick-list" class="meals-list-container">
                       <!-- Content -->
                   </div>
               </div>

               <!-- Protein Efficiency Section -->
               <div class="profile-section">
                   ${UI.renderTape('80px', -1.5)}
                   <div class="profile-section-header">
                       <div class="profile-section-icon" style="background:#fef2f2; color:#ef4444;">${iconTarget}</div>
                       <div style="flex:1">
                           <div class="profile-section-title">蛋白效力参考数据</div>
                           <div class="profile-section-subtitle">性价比计算基本单位</div>
                       </div>
                       <button class="btn-ghost btn-xs" onclick="MealsDataModule.editProteinItem(null)">
                           + 自定义
                       </button>
                   </div>

                   <div id="meals-protein-list" class="meals-list-container">
                       <!-- Custom Data -->
                   </div>
                   
                   <div id="meals-system-list" class="system-data-zone" style="display:none">
                       <div class="system-data-header">系统预设基准 (不可编辑)</div>
                       <div class="meals-list-container" id="meals-system-content"></div>
                   </div>
               </div>
            </div>
        `;

        this.renderQuickList();
        this.renderProteinList();
    },

    // --- Quick List Logic ---
    renderQuickList() {
        const listEl = document.getElementById('meals-quick-list');
        if (!listEl) return;

        // 检查数据是否已加载
        const isLoaded = window.QuickInputModule && window.QuickInputModule._loaded;
        const favorites = window.QuickInputModule ? window.QuickInputModule.getFavorites() : [];

        // 未加载完成 - 显示加载中
        if (!isLoaded) {
            listEl.innerHTML = `
                <div class="loading-hint">
                    <div class="loading-spinner"></div>
                    <div>加载中...</div>
                </div>
            `;
            return;
        }

        // 已加载但为空 - 显示空状态
        if (favorites.length === 0) {
            listEl.innerHTML = `
                <div class="empty-hint">
                    <div>暂无快捷记录</div>
                </div>
            `;
            return;
        }

        // Icons
        const iconDelete = `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round"></path></svg>`;
        const iconEye = `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        const iconEyeOff = `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858-5.608a10.454 10.454 0 012.122-.363c4.478 0 8.268 2.943 9.543 7a10.05 10.05 0 01-2.172 4.147a49.97 49.97 0 01-3.32 3.142M15 12a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 3l18 18" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        // "Play" button icon changed to "Add/Log" style (Circle Plus)
        const iconAddLog = `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        // Drag Handle Icon (6 dots)
        const iconDrag = `<svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24" style="opacity:0.6"><path d="M8 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm0 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm-4 6a2 2 0 1 1 4 0 2 2 0 0 1-4 0Zm8-12a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm0 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm-4 6a2 2 0 1 1 4 0 2 2 0 0 1-4 0Z"></path></svg>`;
        // Pin To Top Icon
        const iconTop = `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 20h14M12 17V4M5 11l7-7 7 7"></path></svg>`;

        // Expand/Collapse Logic (No Pages)
        const total = favorites.length;
        const limit = 5;
        const showAll = this.isExpanded || total <= limit;

        const visibleItems = showAll ? favorites : favorites.slice(0, limit);

        let html = visibleItems.map((fav, i) => {
            const isActive = fav.isActive !== false;
            // Show Pin if item is outside the "Top 5"
            const showPin = i >= 5;

            return `
            <div class="meals-item ${!isActive ? 'inactive' : ''}" data-id="${fav.id}" data-index="${i}">
                <div class="meals-item-icon">
                    ${i + 1}
                </div>
                
                <div class="meals-item-content">
                    <div class="meals-item-title">${fav.title}</div>
                    <div class="meals-item-meta">${this._formatSummary(fav)}</div>
                </div>

                <div class="meals-item-actions">
                    ${showPin ? `
                    <button class="btn-action-icon" onclick="MealsDataModule.moveToTop('${fav.id}')" title="置顶">
                        ${iconTop}
                    </button>` : ''}
                    <button class="btn-action-icon" onclick="MealsDataModule.executeQuick('${fav.id}')" title="填入当天日记">
                        ${iconAddLog}
                    </button>
                    <button class="btn-action-icon" onclick="MealsDataModule.toggleActive('${fav.id}')" title="${isActive ? '停用' : '启用'}">
                        ${isActive ? iconEye : iconEyeOff}
                    </button>
                    <button class="btn-action-icon danger" onclick="MealsDataModule.deleteQuick('${fav.id}')" title="删除">
                        ${iconDelete}
                    </button>
                     <div class="drag-handle" title="拖动排序">${iconDrag}</div>
                </div>
            </div>`;
        }).join('');

        // Expand Control
        if (total > limit) {
            const iconChevronDown = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"></path></svg>`;
            const iconChevronUp = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 15l7-7 7 7"></path></svg>`;
            html += `
            <div class="meals-pagination" style="display:flex; justify-content:center; align-items:center; margin-top:12px; padding-top:12px; border-top:1px solid var(--color-border-subtle);">
                <button class="btn-ghost btn-xs" onclick="MealsDataModule.toggleExpand()">
                    ${showAll ? `${iconChevronUp} 收起` : `${iconChevronDown} 展开全部 (${total})`}
                </button>
            </div>`;
        }

        listEl.innerHTML = html;

        this._initDragAndDrop(listEl);
    },

    toggleExpand() {
        this.isExpanded = !this.isExpanded;
        this.renderQuickList();
    },

    moveToTop(id) {
        if (!window.QuickInputModule) return;
        const favs = window.QuickInputModule.templates;
        const idx = favs.findIndex(f => f.id === id);
        if (idx > 0) {
            const item = favs.splice(idx, 1)[0];
            favs.unshift(item);

            // Update Module
            window.QuickInputModule.templates = favs;

            // Persist Order
            const newOrderIds = favs.map(f => f.id);
            console.log('[MealsData] Pin to top, saving order...', newOrderIds);
            if (API && API.reorderDietTemplates) {
                API.reorderDietTemplates(newOrderIds).catch(err => console.error('[MealsData] Reorder failed:', err));
            } else {
                console.error('[MealsData] API.reorderDietTemplates not found');
            }

            // Trigger refresh
            if (window.SidebarModule) window.SidebarModule.refreshFavorites();
            this.renderQuickList();
        }
    },

    _initDragAndDrop(container) {
        // 使用 SortableJS 提供流畅的拖拽体验
        if (typeof Sortable === 'undefined') {
            console.warn('[MealsData] SortableJS not loaded');
            return;
        }

        Sortable.create(container, {
            animation: 150,
            handle: '.drag-handle',
            draggable: '.meals-item', // Only drag items, not pagination controls
            ghostClass: 'meals-item-ghost',
            chosenClass: 'meals-item-chosen',
            dragClass: 'meals-item-drag',
            onEnd: () => {
                this._saveOrder(container);
                // 重新渲染以更新序号
                this.renderQuickList();
            }
        });
    },

    _saveOrder(container) {
        // Collect new order from DOM
        if (!window.QuickInputModule) return;

        const newOrderIds = [...container.querySelectorAll('.meals-item')].map(el => el.getAttribute('data-id'));
        const allFavs = window.QuickInputModule.templates;

        // Reorder: First take visible items in their new order
        const reorderedPart = [];
        newOrderIds.forEach(id => {
            const item = allFavs.find(f => f.id === id);
            if (item) reorderedPart.push(item);
        });

        // Then append hidden items (if any, preserving their relative order)
        // Filter out items that are already in reorderedPart
        const reorderedIds = new Set(newOrderIds);
        const hiddenPart = allFavs.filter(f => !reorderedIds.has(f.id));

        const newFavs = [...reorderedPart, ...hiddenPart];

        // Replace
        window.QuickInputModule.templates = newFavs;

        // Persist Order
        const finalOrderIds = newFavs.map(f => f.id);
        console.log('[MealsData] Drag end, saving order...', finalOrderIds);
        if (API && API.reorderDietTemplates) {
            API.reorderDietTemplates(finalOrderIds).catch(err => {
                console.error('[Meals] Save order failed', err);
            });
        }

        // Refresh sidebar
        if (window.SidebarModule) window.SidebarModule.refreshFavorites();
    },

    _formatSummary(fav) {
        if (!fav.summary) return '无详细数据';
        let e = Number(fav.summary.energy) || 0; // Stored as kcal
        const w = Math.round(fav.summary.weight || 0);
        let unit = 'kJ';

        // Calculate item count (Leaf nodes)
        let count = 0;
        const outputData = fav.parsedData || fav.templateData || fav.savedData;
        if (outputData) {
            if (Array.isArray(outputData.dishes)) {
                count = outputData.dishes.reduce((acc, d) => acc + (d.ingredients && d.ingredients.length > 0 ? d.ingredients.length : 1), 0);
            } else if (Array.isArray(outputData.ingredients)) {
                count = outputData.ingredients.length;
            }
        }

        // Unit Conversion
        let useKcal = false;
        if (window.ProfileModule) {
            const p = window.ProfileModule.getCurrentProfile();
            if (p && p.diet && p.diet.energy_unit === 'kcal') useKcal = true;
        }

        if (useKcal) {
            unit = 'kcal';
            e = Math.round(e);
        } else {
            e = Math.round(e * 4.184);
        }

        let html = `<span>${e} ${unit}</span> · <span>${w}g</span>`;
        if (count > 0) {
            html += ` · <span>${count}种成分</span>`;
        }
        return html;
    },

    toggleActive(id) {
        if (window.QuickInputModule) {
            const favs = window.QuickInputModule.getFavorites();
            const item = favs.find(f => f.id === id);
            if (item) {
                item.isActive = item.isActive === false ? true : false;
                if (!item.templateData) item.templateData = {};
                item.templateData.isActive = item.isActive;

                API.updateDietTemplate(id, { title: item.title, template_data: item.templateData }).then(() => {
                    if (window.ToastUtils) ToastUtils.show(item.isActive ? '已启用' : '已停用', 'success');
                    this.renderQuickList();
                    if (window.SidebarModule) window.SidebarModule.refreshFavorites();
                });
            }
        }
    },

    deleteQuick(id) {
        if (!window.QuickInputModule) return;

        const favs = window.QuickInputModule.templates;
        const fav = favs.find(f => f.id === id);
        const title = fav ? fav.title : '记录';

        // 使用自定义确认对话框
        this._showConfirmDialog(
            '操作确认',
            `确定要从快捷记录移除「${title}」吗？`,
            () => {
                API.deleteDietTemplate(id).then(() => {
                    const idx = favs.findIndex(f => f.id === id);
                    if (idx > -1) favs.splice(idx, 1);
                    this.renderQuickList();
                    if (window.SidebarModule) window.SidebarModule.refreshFavorites();
                    if (window.ToastUtils) ToastUtils.show(`已移除「${title}」`, 'success');
                }).catch(err => {
                    if (window.ToastUtils) ToastUtils.show('移除失败', 'error');
                });
            }
        );
    },

    executeQuick(id) {
        if (window.QuickInputModule) {
            window.QuickInputModule.executeFavorite(id);
            if (window.DashboardUIModule) window.DashboardUIModule.switchView('analysis');
        }
    },

    // --- Protein List Logic ---
    renderProteinList() {
        const customEl = document.getElementById('meals-protein-list');
        const systemEl = document.getElementById('meals-system-content');
        const systemContainer = document.getElementById('meals-system-list');

        if (!customEl) return;

        let data = window.ProteinReportModule ? (window.ProteinReportModule.rawFoodData || []) : [];
        const indexedData = data.map((item, idx) => ({ ...item, _originalIdx: idx }));

        const customItems = indexedData.filter(i => !i.isSystem);
        const systemItems = indexedData.filter(i => i.isSystem);

        const iconEdit = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round"></path></svg>`;
        const iconDelete = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round"></path></svg>`;

        const renderItem = (item) => `
            <div class="meals-item ${item.isSystem ? 'is-system' : ''}">
                <div class="meals-item-icon" style="background:${item.color}; color:${item.text || '#fff'}; border:none;">
                    ${item.icon}
                </div>
                <div class="meals-item-content">
                     <div class="meals-item-title" style="font-size:0.95rem;">${item.name}</div>
                     <div class="meals-item-meta">
                         <span>¥${item.unit_price} / ${item.measure_mode === 'per_100g' ? '100g' : '份'}${item.serving_weight ? ` (${item.serving_weight}g)` : ''}</span>
                         <span style="border-left:1px solid #ddd; padding-left:8px;">P: ${item.label_macros.p}g</span>
                     </div>
                </div>
                ${!item.isSystem ? `
                <div class="meals-item-actions">
                    <button class="btn-action-icon" onclick="MealsDataModule.editProteinItem(${item._originalIdx})" title="编辑">${iconEdit}</button>
                    <button class="btn-action-icon danger" onclick="MealsDataModule.deleteProteinItem(${item._originalIdx})" title="删除">${iconDelete}</button>
                </div>
                ` : '<div style="padding:0 12px; opacity:0.4; display:flex; align-items:center;"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg></div>'}
            </div>
        `;

        if (customItems.length === 0) {
            customEl.innerHTML = `<div class="empty-hint" style="padding:20px; font-style:italic;">暂无自定义数据</div>`;
        } else {
            customEl.innerHTML = customItems.map(renderItem).join('');
        }

        if (systemItems.length > 0) {
            systemContainer.style.display = 'block';
            systemEl.innerHTML = systemItems.map(renderItem).join('');
        } else {
            systemContainer.style.display = 'none';
        }
    },

    // ... reused modal logic ...
    editProteinItem(idx) {
        this._injectModal(); // 确保 Modal 已注入

        const data = window.ProteinReportModule ? window.ProteinReportModule.rawFoodData : [];
        const isEdit = idx !== null && data[idx];
        if (isEdit && data[idx].isSystem) { if (window.ToastUtils) ToastUtils.show('系统数据不可编辑', 'warning'); return; }

        const item = isEdit ? data[idx] : { name: '', icon: '🥩', color: '#ff7675', unit_price: 0, measure_mode: 'per_100g', serving_weight: 100, label_macros: { p: 0, e: 0, f: 0 } };

        const html = `
            <div class="md-input-group">
                <label>名称 & 图标</label>
                <div style="display:flex; gap:12px;">
                    <input id="pi-icon" class="md-input" style="width:70px; text-align:center; font-size:1.5rem;" value="${item.icon}" placeholder="🥩">
                    <input id="pi-name" class="md-input" value="${item.name}" placeholder="e.g. 鸡胸肉">
                </div>
            </div>
             <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                <div class="md-input-group"><label>价格 (元)</label><input type="number" id="pi-price" class="md-input" value="${item.unit_price}" step="0.1"></div>
                <div class="md-input-group"><label>计量方式</label><select id="pi-mode" class="md-input"><option value="per_100g" ${item.measure_mode === 'per_100g' ? 'selected' : ''}>每 100g</option><option value="per_serving" ${item.measure_mode === 'per_serving' ? 'selected' : ''}>每份</option></select></div>
            </div>
            <div class="md-input-group" id="pi-weight-group" style="${item.measure_mode === 'per_100g' ? 'display:none' : ''}"><label>每份重量 (g)</label><input type="number" id="pi-weight" class="md-input" value="${item.serving_weight || 0}"></div>
            <div class="md-input-group"><label>营养素 (每计量单位)</label><div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
                <div><label style="font-size:0.7rem;color:#888">蛋白(g)</label><input type="number" id="pi-p" class="md-input" value="${item.label_macros.p}"></div>
                <div><label style="font-size:0.7rem;color:#888">热量(kJ)</label><input type="number" id="pi-e" class="md-input" value="${item.label_macros.e}"></div>
                <div><label style="font-size:0.7rem;color:#888">脂肪(g)</label><input type="number" id="pi-f" class="md-input" value="${item.label_macros.f}"></div>
            </div></div>
            <div class="md-input-group"><label>颜色</label><div class="md-swatches">${['#55efc4', '#a29bfe', '#74b9ff', '#ff7675', '#ffd93d', '#fdcb6e', '#e17055', '#6c5ce7'].map(c => `<div class="md-swatch ${c === item.color ? 'selected' : ''}" style="background:${c}" onclick="this.parentNode.querySelectorAll('.md-swatch').forEach(e=>e.classList.remove('selected')); this.classList.add('selected');" data-color="${c}"></div>`).join('')}</div></div>
        `;

        const modal = document.querySelector('#meals-modal .md-modal');
        document.querySelector('#meals-modal #md-title').textContent = isEdit ? '编辑' : '添加';
        document.getElementById('md-content').innerHTML = html;
        document.getElementById('pi-mode').onchange = (e) => { document.getElementById('pi-weight-group').style.display = e.target.value === 'per_serving' ? 'block' : 'none'; };

        this.openModal(async () => {
            const newItem = {
                id: isEdit ? item.id : 'custom_' + Date.now(),
                name: document.getElementById('pi-name').value,
                icon: document.getElementById('pi-icon').value,
                measure_mode: document.getElementById('pi-mode').value,
                unit_price: parseFloat(document.getElementById('pi-price').value) || 0,
                serving_weight: parseFloat(document.getElementById('pi-weight').value) || 0,
                label_macros: { p: parseFloat(document.getElementById('pi-p').value) || 0, e: parseFloat(document.getElementById('pi-e').value) || 0, f: parseFloat(document.getElementById('pi-f').value) || 0 },
                color: document.querySelector('.md-swatch.selected')?.dataset.color || '#ccc',
                text: '#fff',
                isSystem: false
            };
            if (window.ProteinReportModule) {
                if (isEdit) window.ProteinReportModule.rawFoodData[idx] = newItem;
                else window.ProteinReportModule.rawFoodData.unshift(newItem);
                this.renderProteinList();
            }
            return true;
        });
    },

    _injectModal() {
        if (document.getElementById('meals-modal')) return;
        const div = document.createElement('div');
        div.id = 'meals-modal'; div.className = 'md-modal-overlay';
        div.innerHTML = `<div class="md-modal"><h3 id="md-title" style="margin-top:0; margin-bottom: 20px; font-size: 1.25rem;">编辑</h3><div id="md-content"></div><div style="display:flex; justify-content:flex-end; gap:12px; margin-top:28px;"><button class="btn btn-secondary" onclick="MealsDataModule.closeModal()">取消</button><button class="btn btn-primary" id="md-confirm">确认</button></div></div>`;
        document.body.appendChild(div);
    },
    openModal(cb) {
        this._injectModal(); // 确保 Modal 已注入
        const el = document.getElementById('meals-modal');
        el.classList.add('visible');
        const btn = document.getElementById('md-confirm');
        const nBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(nBtn, btn);
        nBtn.onclick = async () => { if (await cb()) this.closeModal(); };
    },
    closeModal() { document.getElementById('meals-modal').classList.remove('visible'); },

    /**
     * 显示自定义确认对话框
     * @param {string} title - 标题
     * @param {string} message - 提示消息
     * @param {Function} onConfirm - 确认回调
     */
    _showConfirmDialog(title, message, onConfirm) {
        this._injectModal(); // 确保 Modal 已注入

        const html = `
            <div style="text-align:center; padding:8px 0;">
                <p style="margin:0 0 16px; color:#666; font-size:0.95rem;">${message}</p>
            </div>
        `;
        document.querySelector('#meals-modal #md-title').textContent = title;
        document.getElementById('md-content').innerHTML = html;

        // 修改确认按钮样式为危险色
        const confirmBtn = document.getElementById('md-confirm');
        confirmBtn.textContent = '确认移除';
        confirmBtn.style.background = '#ef4444';
        confirmBtn.style.borderColor = '#ef4444';

        this.openModal(async () => {
            onConfirm();
            // 恢复按钮样式
            confirmBtn.textContent = '确认';
            confirmBtn.style.background = '';
            confirmBtn.style.borderColor = '';
            return true;
        });
    },
    showPriceInputModal(session, callback) {
        this._injectModal(); // 确保 Modal 已注入

        const html = `<div class="md-input-group"><p style="margin-bottom:12px; color:#555;">请输入本餐的预估总价。</p><label>总金额 (元)</label><input type="number" id="pi-session-price" class="md-input" placeholder="0.0" step="0.1" style="font-size:1.5rem; text-align:center;"></div>`;
        document.querySelector('#meals-modal #md-title').textContent = '标记价格';
        document.getElementById('md-content').innerHTML = html;
        setTimeout(() => document.getElementById('pi-session-price').focus(), 100);
        this.openModal(async () => {
            const val = parseFloat(document.getElementById('pi-session-price').value);
            if (!isNaN(val)) { callback(val); return true; }
            return false;
        });
    }
};

window.MealsDataModule = MealsDataModule;
