/**
 * Sidebar 侧边栏管理模块 (MVP 2.2)
 * 负责渲染双层导航 (Dialogues > Cards) 和最近卡片
 */
import { EmojiIcon } from '../utils/icons.js';

const SidebarModule = {
    // 状态
    dialogues: [],
    currentDialogueId: null,
    collapsedStates: {}, // 记录折叠状态 { dialogueId: boolean }

    // DOM 元素缓存
    el: {
        container: null,
        dialogueList: null,
    },

    // 状态
    menuState: {
        visible: false,
        targetId: null,
        targetType: null, // 'dialogue' | 'card'
        targetObject: null
    },

    init() {
        this.el.container = document.getElementById('history-panel');
        this.el.dialogueList = document.getElementById('dialogue-list-container');

        // Inject Modal and Menu HTML
        this._injectComponents();

        // 绑定事件委托
        if (this.el.dialogueList) {
            this.el.dialogueList.addEventListener('click', (e) => this.handleSidebarClick(e));
        }

        // Global events (close menu on click)
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#context-menu') && !e.target.closest('.action-btn')) {
                this.closeContextMenu();
            }
        });

        // Modal inputs
        const modal = document.getElementById('rename-modal-overlay');
        const input = document.getElementById('rename-input');
        const confirmBtn = document.getElementById('rename-confirm');
        const cancelBtn = document.getElementById('rename-cancel');

        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.closeRenameModal();
            });
            cancelBtn.addEventListener('click', () => this.closeRenameModal());
            confirmBtn.addEventListener('click', () => this.confirmRename());

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.confirmRename();
                if (e.key === 'Escape') this.closeRenameModal();
            });
        }

        // 绑定新对话按钮
        const newBtn = document.getElementById('new-dialogue-btn');
        if (newBtn && window.Dashboard) {
            newBtn.addEventListener('click', () => window.Dashboard.createNewDialogue());
        }

        // 初始加载: 同时加载对话和最近卡片
        this.loadRecentCards();
        this.loadDialogues();
    },

    /**
     * 加载最近卡片
     */
    async loadRecentCards() {
        try {
            const cards = await API.getRecentCards();
            this.recentCards = cards;
            // 如果对话已经加载完，就重绘。如果没加载完，loadDialogues会处理重绘
            if (this.dialogues.length > 0) {
                this.render();
            }
        } catch (error) {
            console.error('Failed to load recent cards:', error);
        }
    },

    /**
     * 加载对话列表
     */
    async loadDialogues() {
        // console.log('[Sidebar] loadDialogues called');
        if (!this.el.dialogueList) return;

        try {
            // 只在完全空白时显示 loading (避免刷新闪烁)
            const hasContent = this.el.dialogueList.querySelector('.dialogue-item, .empty-sidebar');
            if (!hasContent) {
                this.renderSkeleton();
            }

            const dialogues = await API.getDialogues();
            this.dialogues = dialogues;

            // 如果没有数据，显示空状态
            if (dialogues.length === 0) {
                this.renderEmptyState();
                return;
            }

            // 自动选中最近的一个 (如果当前未选中，且非 Demo 模式)
            // Demo 模式下由 DemoModule 控制加载顺序，避免重复加载导致消息重复
            const isDemo = new URLSearchParams(window.location.search).get('demo') === 'true';

            if (this.dialogues.length > 0 && !this.currentDialogueId && !isDemo) {
                const recentId = this.dialogues[0].id;
                this.currentDialogueId = recentId;

                // 默认展开选中项
                this.collapsedStates[recentId] = false;

                // 在右侧加载消息
                setTimeout(() => {
                    if (window.Dashboard && window.Dashboard.loadDialogue) {
                        window.Dashboard.loadDialogue(recentId);
                    }
                }, 0);
            }

            // 渲染列表
            this.render();

        } catch (error) {
            console.error('Failed to load dialogues:', error);
            if (this.dialogues.length === 0) {
                this.el.dialogueList.innerHTML = '<div class="error-placeholder">加载失败，请刷新重试</div>';
            }
        }
    },

    /**
     * 加载单个对话的卡片详情 (用于展开时)
     * @param {string} dialogueId 
     * @returns {Promise<Array>} cards
     */
    async loadDialogueCards(dialogueId) {
        try {
            const cards = await API.getCards(dialogueId);
            return cards;
        } catch (error) {
            console.error(`Failed to load cards for dialogue ${dialogueId}:`, error);
            return [];
        }
    },

    /**
     * 渲染完整列表 (Recent + Dialogues)
     */
    render() {
        if (!this.el.dialogueList) return;

        let html = '';

        // 1. 渲染最近卡片区 (Recent Cards)
        if (this.recentCards && this.recentCards.length > 0) {
            html += this.renderRecentSection();
        }

        // 2. 渲染对话列表 (按日期分组)
        // 使用 DateFormatter 分组更好，但这里可以保持按 Day 分组
        const groups = this.groupDialoguesByDate(this.dialogues);

        // 渲染对话分组
        for (const [groupName, groupDialogues] of Object.entries(groups)) {
            if (groupDialogues.length === 0) continue;

            html += `<div class="dialogue-section-title">${groupName}</div>`;

            groupDialogues.forEach(dialogue => {
                const isCollapsed = this.collapsedStates[dialogue.id] ?? true; // 默认折叠
                const isActive = dialogue.id === this.currentDialogueId;
                const titleCtx = this.getDialogueDisplayTitle(dialogue);

                html += `
                    <div class="dialogue-item ${isActive ? 'active' : ''} ${isCollapsed ? 'collapsed' : 'expanded'}" 
                         data-id="${dialogue.id}"
                         data-type="dialogue"
                    >
                        <div class="dialogue-header">
                            <span class="expand-icon">${isCollapsed ? '▶' : '▼'}</span>
                            <span class="dialogue-icon">${EmojiIcon.render('type-dialogue')}</span>
                            <div class="dialogue-title-container">
                                <span class="dialogue-title" title="${this.escapeHtml(titleCtx.full)}">${this.escapeHtml(titleCtx.display)}</span>
                            </div>
                            <div class="dialogue-actions">
                                <button class="action-btn dialogue-menu-btn" title="更多">⋮</button>
                            </div>
                        </div>
                        <div class="dialogue-cards-container" id="cards-container-${dialogue.id}">
                            <!-- 卡片内容将按需加载或预渲染 -->
                            ${!isCollapsed ? '<div class="cards-loading">加载中...</div>' : ''}
                        </div>
                    </div>
                `;

                // 如果是展开状态，触发展开逻辑（异步加载卡片）
                if (!isCollapsed) {
                    setTimeout(() => this.expandDialogue(dialogue.id), 0);
                }
            });
        }

        // 如果 totally empty
        if (!html) {
            this.renderEmptyState();
            return;
        }

        this.el.dialogueList.innerHTML = html;

        // 渲染 Emoji (如果有需要替换的)
        if (window.EmojiIcon && window.EmojiIcon.replaceAll) {
            window.EmojiIcon.replaceAll();
        }
    },

    renderRecentSection() {
        // 优先显示 Quick Favorites (快捷收藏)
        let favorites = [];
        if (window.QuickInputModule && window.QuickInputModule.getFavorites) {
            favorites = window.QuickInputModule.getFavorites();
        }

        // 如果没有收藏，显示提示或空 (根据用户要求“调整位置”，这里显示收藏列表)
        // 限制显示前 3 个
        const displayItems = favorites.slice(0, 3);

        if (displayItems.length === 0) {
            // Optional: fallback to recent cards or show "Add Favorite" hint
            // render original recent cards if no favorites? 
            // The user said "Adjust position to Quick Record...". Ill show placeholder if empty.
            return `
                <div class="recent-cards-section">
                    <div class="dialogue-section-title">快捷记录</div>
                    <div style="padding: 8px 12px; color: var(--color-text-muted); font-size: 0.8rem; font-style: italic;">
                        ${(typeof Auth !== 'undefined' && Auth.isDemoMode && Auth.isDemoMode())
                    ? '注册登录后<br>可建立您的专属饮食模板，一键添加'
                    : '暂无收藏模板<br>在分析结果中点击 ⭐ 收藏'}
                    </div>
                </div>
            `;
        }

        let html = '';
        // Get global unit preference
        let unit = 'kJ';
        if (window.ProfileModule) {
            const p = window.ProfileModule.getCurrentProfile();
            if (p && p.diet && p.diet.energy_unit === 'kcal') unit = 'kcal';
        }

        displayItems.forEach(item => {
            // Item structure: { id, title, summary: { energy, weight }, addedAt }
            const typeIcon = EmojiIcon.render('type-diet'); // Assume Diet for templates
            const title = this.escapeHtml(item.title || '未命名模板');

            let subtitle = '快捷模板';
            if (item.summary) {
                const eVal = Number(item.summary.energy) || 0;
                const wVal = Math.round(Number(item.summary.weight) || 0);

                let displayE = 0;
                if (unit === 'kcal') {
                    displayE = Math.round(eVal);
                } else {
                    displayE = Math.round(eVal * 4.184); // Auto convert roughly or use utils if available
                }

                // Format: 模板1200kJ 模板300g
                subtitle = `模板${displayE}${unit} 模板${wVal}g`;
            }

            html += `
                 <div class="card-item-recent quick-template-item" data-id="${item.id}" data-action="quick-template">
                     <div class="card-recent-left">
                        <span class="card-icon" style="filter: hue-rotate(45deg);">${typeIcon}</span>
                        <div class="card-info">
                            <span class="card-title"><span class="fav-star">⭐</span> ${title}</span>
                            <span class="card-time">${subtitle}</span>
                        </div>
                     </div>
                     <div class="card-actions">
                         <button class="action-btn card-menu-btn" title="更多">⋮</button>
                     </div>
                 </div>
             `;
        });

        return `
            <div class="recent-cards-section">
                <div class="dialogue-section-title">快捷记录 (Top 3)</div>
                <div class="recent-cards-list">
                    ${html}
                </div>
            </div>
        `;
    },

    getDialogueDisplayTitle(dialogue) {
        // 1. User Title takes precedence
        if (dialogue.user_title) {
            return { display: dialogue.user_title, full: dialogue.user_title };
        }

        // 2. Logic: x msgs, y cards
        // need to estimate counts or use what's available
        // backend Dialogue model has messages[] and card_ids[]
        const msgCount = (dialogue.messages || []).length;
        const cardCount = (dialogue.card_ids || []).length;

        let autoTitle = "";
        if (msgCount === cardCount && cardCount > 0) {
            autoTitle = `${cardCount}个分析结果`;
        } else {
            autoTitle = `${msgCount}条消息 ${cardCount}个分析`;
        }

        if (msgCount === 0 && cardCount === 0) autoTitle = "新对话";

        return { display: autoTitle, full: autoTitle };
    },


    /**
     * 处理点击事件
     */
    handleSidebarClick(e) {
        // Menu Buttons
        const dialogueMenuBtn = e.target.closest('.dialogue-menu-btn');
        if (dialogueMenuBtn) {
            e.stopPropagation();
            const item = dialogueMenuBtn.closest('.dialogue-item');
            const dialogueId = item.dataset.id;
            const dialogue = this.dialogues.find(d => d.id === dialogueId);
            this.showContextMenu(e, 'dialogue', dialogue);
            return;
        }

        const cardMenuBtn = e.target.closest('.card-menu-btn');
        if (cardMenuBtn) {
            e.stopPropagation();
            const item = cardMenuBtn.closest('.card-item-nested, .card-item-recent');

            if (item.classList.contains('quick-template-item')) {
                const favId = item.dataset.id;
                let currentTitle = '';
                if (window.QuickInputModule && window.QuickInputModule.getFavorites) {
                    const favs = window.QuickInputModule.getFavorites();
                    const found = favs.find(f => f.id === favId);
                    if (found) currentTitle = found.title;
                }
                this.showContextMenu(e, 'favorite', { id: favId, user_title: currentTitle, title: currentTitle });
                return;
            }
            const cardId = item.dataset.id;
            const dialogueId = item.dataset.dialogueId;
            // Need to find card object. This might be in recentCards OR need to be fetched/found if loaded.
            // Simplified: we try to find in recentCards first, or if expanded, we don't track all loaded cards globally in this module easily.
            // For Sidebar, we usually only have full data for 'recentCards' or 'dialogues'.
            // For nested cards, we load them on fly. We might need to store them or just carry minimal data.
            // Let's rely on finding it or creating a proxy object if we only need ID for rename.
            let card = this.recentCards ? this.recentCards.find(c => c.id === cardId) : null;
            if (!card) {
                // If not in recent, maybe we can fetch it or just use ID. 
                // For rename, we need current title to prefill.
                const titleEl = item.querySelector('.card-title');
                card = { id: cardId, user_title: titleEl ? titleEl.textContent : '', dialogue_id: dialogueId };
            }
            this.showContextMenu(e, 'card', card);
            return;
        }

        const header = e.target.closest('.dialogue-header');
        if (header) {
            const item = header.parentElement;
            const dialogueId = item.dataset.id;
            this.toggleDialogue(dialogueId, false);
            this.currentDialogueId = dialogueId;
            if (window.Dashboard && window.Dashboard.loadDialogue) {
                window.Dashboard.loadDialogue(dialogueId);
            }
            this.render();
            return;
        }

        const quickTemplate = e.target.closest('[data-action="quick-template"]');
        if (quickTemplate) {
            const cardId = quickTemplate.dataset.id;
            if (window.QuickInputModule) {
                window.QuickInputModule.executeFavorite(cardId);
                // Close mobile sidebar
                document.body.classList.remove('sidebar-open');
            }
            return;
        }

        const cardItem = e.target.closest('.card-item-nested, .card-item-recent');
        if (cardItem) {
            const cardId = cardItem.dataset.id;
            const dialogueId = cardItem.dataset.dialogueId;
            this.selectCard(cardId, dialogueId);
            return;
        }
    },

    // ========== Context Menu Logic ==========

    showContextMenu(event, type, object) {
        this.menuState = { visible: true, targetType: type, targetObject: object };

        const menu = document.getElementById('context-menu');
        const renameBtn = document.getElementById('context-rename');

        if (!menu) return;

        // Position menu
        const rect = event.target.getBoundingClientRect();
        menu.style.top = `${rect.bottom + 4}px`;
        menu.style.left = `${rect.left}px`;
        menu.classList.remove('hidden');

        // Bind click once
        renameBtn.onclick = () => {
            this.closeContextMenu();
            this.openRenameModal(type, object);
        };
    },

    closeContextMenu() {
        const menu = document.getElementById('context-menu');
        if (menu) menu.classList.add('hidden');
        this.menuState = { visible: false, targetType: null, targetObject: null };
    },

    // ========== Rename Modal Logic ==========

    openRenameModal(type, object) {
        if (!object) return;

        const modal = document.getElementById('rename-modal-overlay');
        const input = document.getElementById('rename-input');
        const title = document.getElementById('rename-modal-title');

        if (!modal || !input) return;

        this.menuState.targetType = type;
        this.menuState.targetObject = object;

        if (type === 'favorite') {
            title.textContent = '重命名快捷餐食';
        } else {
            title.textContent = type === 'dialogue' ? '重命名对话' : '重命名分析结果';
        }
        input.value = object.user_title || (type === 'dialogue' ? '' : object.title) || ''; // Prefill logic
        // If it's a proxy object from nested card, user_title might be the full displayed title. 
        // It's acceptable for now to prefill with whatever we have.

        modal.classList.add('visible');
        setTimeout(() => input.focus(), 50);
    },

    closeRenameModal() {
        const modal = document.getElementById('rename-modal-overlay');
        if (modal) modal.classList.remove('visible');
        this.menuState.targetObject = null;
    },

    async confirmRename() {
        const input = document.getElementById('rename-input');
        const newTitle = input.value.trim();
        const { targetType, targetObject } = this.menuState;

        if (!targetObject) return;

        this.closeRenameModal();

        try {
            if (targetType === 'dialogue') {
                await API.updateDialogue(targetObject.id, { user_title: newTitle });
                await this.loadDialogues(); // Refresh sidebar
            } else if (targetType === 'favorite') {
                if (window.QuickInputModule && window.QuickInputModule.renameFavorite) {
                    window.QuickInputModule.renameFavorite(targetObject.id, newTitle);
                }
            } else {
                // Card
                // We need to fetch the full card to update it properly if we use the full update endpoint, 
                // BUT API.updateCard can probably handle partials if we coded it that way? 
                // Checking api_dialogue.py: router.patch("/api/cards/{card_id}") accepts ResultCard which requires all fields if standard Pydantic. 
                // Wait, in previous step I didn't change update_card to match update_dialogue's partial style.
                // It uses "card_update: ResultCard". 
                // So I strictly need to fetch, modify, save.

                let fullCard = await API.getCard(targetObject.id);
                fullCard.user_title = newTitle;
                await API.updateCard(targetObject.id, fullCard);

                // Refresh logic
                if (this.recentCards.find(c => c.id === targetObject.id)) {
                    await this.loadRecentCards();
                }
                // Also refresh current dialogue view if open
                if (this.currentDialogueId) {
                    // Force re-render of sidebar for nested Items
                    const dId = targetObject.dialogue_id || (fullCard ? fullCard.dialogue_id : null);
                    if (dId) this.expandDialogue(dId);
                }
                this.render(); // Redraw
            }
        } catch (e) {
            console.error("Rename failed", e);
            if (window.ToastUtils) ToastUtils.show("重命名失败", "error");
            else alert("重命名失败");
        }
    },

    _injectComponents() {
        if (document.getElementById('context-menu')) return;

        const body = document.body;

        // Context Menu
        const menuHTML = `
            <div id="context-menu" class="hidden">
                <div class="context-menu-item" id="context-rename">
                    <span class="icon">✎</span> 重命名
                </div>
            </div>
        `;

        // Modal
        const modalHTML = `
            <div id="rename-modal-overlay" class="modal-overlay">
                <div class="modal-content">
                    <div class="modal-title" id="rename-modal-title">重命名</div>
                    <input type="text" id="rename-input" class="modal-input" placeholder="输入新标题...">
                    <div class="modal-actions">
                        <button class="modal-btn cancel" id="rename-cancel">取消</button>
                        <button class="modal-btn confirm" id="rename-confirm">保存</button>
                    </div>
                </div>
            </div>
        `;

        const div = document.createElement('div');
        div.innerHTML = menuHTML + modalHTML;
        while (div.firstChild) {
            body.appendChild(div.firstChild);
        }
    },

    _getFavMark(cardId) {
        if (window.QuickInputModule && window.QuickInputModule.isFavorite && window.QuickInputModule.isFavorite(cardId)) {
            return '<span class="fav-star">⭐</span>';
        }
        return '';
    },

    /**
     * 切换对话折叠状态
     */
    async toggleDialogue(dialogueId, shouldRender = true) {
        const isCollapsed = this.collapsedStates[dialogueId] ?? true;
        this.collapsedStates[dialogueId] = !isCollapsed;

        // 仅重新渲染该项或局部更新 DOM
        if (shouldRender) {
            this.render(); // 简单起见重绘，优化可考虑 partial update
        }
    },

    /**
     * 展开并加载卡片
     */
    async expandDialogue(dialogueId) {
        const container = document.getElementById(`cards-container-${dialogueId}`);
        if (!container) return;

        // 如果已经有内容且不是 loading，就不重载了 (简单缓存)
        // 但为了状态实时性，这里我们先每次都加载

        const cards = await this.loadDialogueCards(dialogueId);

        if (cards.length === 0) {
            container.innerHTML = '<div class="no-cards-hint">无关联分析结果</div>';
            return;
        }

        let html = '';
        cards.forEach(card => {
            const statusIcon = this.getStatusIcon(card.status);
            const typeIcon = card.mode === 'diet' ? EmojiIcon.render('type-diet') : EmojiIcon.render('type-keep');

            // 计算动态标题
            const dynamicTitle = card.user_title || this._getDynamicCardTitle(card) || card.title;

            let timeDisplay = '';
            if (window.DateFormatter) {
                timeDisplay = window.DateFormatter.formatSmart(card.updated_at || card.created_at);
            }

            html += `
                <div class="card-item-nested" data-id="${card.id}" data-dialogue-id="${dialogueId}">
                    <span class="card-status-indicator ${card.status}"></span>
                    <div class="card-nested-left">
                        <span class="card-icon">${typeIcon}</span>
                        <div class="card-info">
                            <span class="card-title">${this._getFavMark(card.id)} ${this.escapeHtml(dynamicTitle)}</span>
                            <span class="card-time">${timeDisplay}</span>
                        </div>
                    </div>
                    <div class="card-actions">
                         <button class="action-btn card-menu-btn" title="更多">⋮</button>
                     </div>
                </div>
            `;
        });

        container.innerHTML = html;

        // Re-run emoji replacement for new content
        if (window.EmojiIcon && window.EmojiIcon.replaceAll) {
            window.EmojiIcon.replaceAll();
        }
    },

    /**
     * 选中卡片
     */
    selectCard(cardId, dialogueId) {
        // 高亮 UI
        document.querySelectorAll('.card-item-nested').forEach(el => el.classList.remove('active'));
        const el = document.querySelector(`.card-item-nested[data-id="${cardId}"]`);
        if (el) el.classList.add('active');

        this.currentDialogueId = dialogueId;

        // Close mobile sidebar
        document.body.classList.remove('sidebar-open');

        // 通知 Dashboard 加载卡片
        if (window.Dashboard && window.Dashboard.loadCard) {
            window.Dashboard.loadCard(cardId);
        }
    },

    // ========== Helpers ==========

    groupDialoguesByDate(dialogues) {
        const groups = { '今天': [], '昨天': [], '更早': [] };
        const today = new Date().setHours(0, 0, 0, 0);
        const yesterday = today - 86400000;

        dialogues.forEach(d => {
            const date = new Date(d.updated_at || d.created_at).setHours(0, 0, 0, 0);
            if (date === today) groups['今天'].push(d);
            else if (date === yesterday) groups['昨天'].push(d);
            else groups['更早'].push(d);
        });

        return groups;
    },

    renderEmptyState() {
        this.el.dialogueList.innerHTML = `
            <div class="empty-sidebar">
                <div class="history-section-title">今天</div>
                <div class="history-item placeholder">暂无记录</div>
            </div>
        `;
    },

    refreshFavorites() {
        this.render();
    },

    getStatusIcon(status) {
        switch (status) {
            case 'saved': return EmojiIcon.render('status-saved');
            case 'draft': return EmojiIcon.render('status-draft');
            case 'analyzing': return EmojiIcon.render('status-analyzing');
            case 'error': return EmojiIcon.render('status-error');
            default: return '';
        }
    },

    renderSkeleton() {
        const skeletonItem = `
            <div class="skeleton-item">
                <div class="skeleton-icon"></div>
                <div class="skeleton-text"></div>
            </div>
        `;
        // Generate a few items to simulate content
        this.el.dialogueList.innerHTML = `
            <div class="dialogue-section-title" style="opacity: 0.5;">加载中</div>
            ${skeletonItem.repeat(3)}
        `;
    },

    escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    /**
     * 根据当前 Profile 配置动态生成标题
     * (解决后端 title "写死" 单位及转换错误的问题)
     * 策略：移除时间前缀（由副标题承担），强化核心指标（体重、食物总重）
     */
    _getDynamicCardTitle(card) {
        if (!card) return '';

        const versions = card.versions || [];
        if (versions.length === 0) return card.title;

        // 取最新版本
        const latestVersion = versions[versions.length - 1];

        let rawData = latestVersion.raw_result || {};

        // 获取全局单位设置
        let unit = 'kJ';
        if (window.ProfileModule) {
            const p = window.ProfileModule.getCurrentProfile();
            if (p && p.diet && p.diet.energy_unit === 'kcal') unit = 'kcal';
        }



        // 分支 1: Diet 模式
        if (card.mode === 'diet') {
            // 兼容 raw_result (后端结构) 和 parsedData (前端结构)
            let dietTime = 'unknown';
            let energyKj = 0;
            let dishes = [];

            if (rawData.meal_summary) {
                // Raw Result Structure
                dietTime = rawData.meal_summary.diet_time;
                energyKj = rawData.meal_summary.total_energy_kj || 0;
                dishes = rawData.dishes || [];
            } else {
                return card.title; // 无法识别的结构
            }

            const timeMap = {
                'snack': '加餐', 'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐'
            };
            const timeDisplay = timeMap[dietTime] || '饮食';

            // 单位转换
            let energyVal = energyKj;
            if (unit === 'kcal') {
                energyVal = energyKj / 4.184;
            }

            // 计算总重 (优先取 Summary，否则遍历计算)
            let totalWeight = 0;

            // Strategy 1: Direct from summary
            if (rawData.meal_summary && rawData.meal_summary.net_weight_g) {
                totalWeight = rawData.meal_summary.net_weight_g;
            }

            // Strategy 2: Sum from dishes if summary failed
            if (!totalWeight && dishes.length > 0) {
                totalWeight = dishes.reduce((sum, dish) => {
                    // Case A: Dish has direct weight (simple structure)
                    if (dish.weight_g) return sum + dish.weight_g;
                    // Case B: Dish has ingredients (nested structure)
                    if (dish.ingredients && Array.isArray(dish.ingredients)) {
                        return sum + dish.ingredients.reduce((iSum, ing) => iSum + (ing.weight_g || 0), 0);
                    }
                    return sum;
                }, 0);
            }

            const weightStr = totalWeight > 0 ? `${Math.round(totalWeight)}g` : '';

            // 移除 dateStr 前缀，只显示内容: "{餐段} {能量} {总重}"
            return `${timeDisplay} ${Math.round(energyVal)}${unit} ${weightStr}`.trim();
        }

        // 分支 2: Keep 模式
        if (card.mode === 'keep') {
            // Keep 的 raw_result 直接包含各事件数组
            const scaleEvents = rawData.scale_events || [];
            const sleepEvents = rawData.sleep_events || [];
            const measureEvents = rawData.body_measure_events || [];

            // 优先显示体重
            if (scaleEvents.length > 0) {
                const weight = scaleEvents[0].weight_kg;
                if (weight) return `体重 ${weight}kg`;
            }

            const count = scaleEvents.length + sleepEvents.length + measureEvents.length;
            // 如果解析失败或为0，fallback
            if (count === 0 && !rawData.scale_events) return card.title;

            return `Keep记录 ${count}项`.trim();
        }

        return card.title;
    }
};

window.SidebarModule = SidebarModule;
