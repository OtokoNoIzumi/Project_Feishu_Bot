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

    init() {
        this.el.container = document.getElementById('history-panel');
        this.el.dialogueList = document.getElementById('dialogue-list-container');

        // 绑定事件委托
        if (this.el.dialogueList) {
            this.el.dialogueList.addEventListener('click', (e) => this.handleSidebarClick(e));
        }

        // 绑定新对话按钮
        const newBtn = document.getElementById('new-dialogue-btn');
        if (newBtn && window.Dashboard) {
            newBtn.addEventListener('click', () => window.Dashboard.createNewDialogue());
        }

        // 初始加载
        this.loadDialogues();
    },

    /**
     * 加载对话列表
     */
    async loadDialogues() {
        if (!this.el.dialogueList) return;

        try {
            // 只在完全空白时显示 loading（避免刷新闪烁）
            const hasContent = this.el.dialogueList.querySelector('.dialogue-item, .empty-sidebar');
            if (!hasContent) {
                this.el.dialogueList.innerHTML = '<div class="loading-placeholder">加载中...</div>';
            }

            const dialogues = await API.getDialogues(); // 假设 API.getDialogues 已返回列表
            this.dialogues = dialogues;

            // 如果没有数据，显示空状态
            if (dialogues.length === 0) {
                this.renderEmptyState();
                return;
            }

            // 渲染列表（直接替换，无闪烁）
            this.render();

        } catch (error) {
            console.error('Failed to load dialogues:', error);
            // 仅当之前没有内容时才显示错误
            if (!this.dialogues.length) {
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
     * 渲染完整列表
     */
    render() {
        if (!this.el.dialogueList) return;

        // 按日期分组 (简单实现：今天 / 昨天 / 更早)
        const groups = this.groupDialoguesByDate(this.dialogues);

        let html = '';

        for (const [groupName, groupDialogues] of Object.entries(groups)) {
            if (groupDialogues.length === 0) continue;

            html += `<div class="dialogue-section-title">${groupName}</div>`;

            groupDialogues.forEach(dialogue => {
                const isCollapsed = this.collapsedStates[dialogue.id] ?? true; // 默认折叠
                const isActive = dialogue.id === this.currentDialogueId;

                html += `
                    <div class="dialogue-item ${isActive ? 'active' : ''} ${isCollapsed ? 'collapsed' : 'expanded'}" 
                         data-id="${dialogue.id}"
                         data-type="dialogue"
                    >
                        <div class="dialogue-header">
                            <span class="expand-icon">${isCollapsed ? '▶' : '▼'}</span>
                            <span class="dialogue-icon">${EmojiIcon.render('type-dialogue')}</span>
                            <span class="dialogue-title">${this.escapeHtml(dialogue.title || '新对话')}</span>
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

        this.el.dialogueList.innerHTML = html;

        // 渲染 Emoji (如果有需要替换的)
        if (window.EmojiIcon && window.EmojiIcon.replaceAll) {
            window.EmojiIcon.replaceAll();
        }
    },

    /**
     * 处理点击事件
     */
    handleSidebarClick(e) {
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

        const cardItem = e.target.closest('.card-item-nested');
        if (cardItem) {
            const cardId = cardItem.dataset.id;
            const dialogueId = cardItem.dataset.dialogueId;
            this.selectCard(cardId, dialogueId);
            return;
        }
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
            container.innerHTML = '<div class="no-cards-hint">无关联卡片</div>';
            return;
        }

        let html = '';
        cards.forEach(card => {
            const statusIcon = this.getStatusIcon(card.status);
            const typeIcon = card.mode === 'diet' ? EmojiIcon.render('type-diet') : EmojiIcon.render('type-keep');

            html += `
                <div class="card-item-nested" data-id="${card.id}" data-dialogue-id="${dialogueId}">
                    <span class="card-status-indicator ${card.status}"></span>
                    <span class="card-icon">${typeIcon}</span>
                    <span class="card-title">${this.escapeHtml(card.title)}</span>
                    <span class="card-status-icon">${statusIcon}</span>
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

    getStatusIcon(status) {
        switch (status) {
            case 'saved': return EmojiIcon.render('status-saved');
            case 'draft': return EmojiIcon.render('status-draft');
            case 'analyzing': return EmojiIcon.render('status-analyzing');
            case 'error': return EmojiIcon.render('status-error');
            default: return '';
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
};

window.SidebarModule = SidebarModule;
