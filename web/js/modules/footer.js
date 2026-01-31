
const FooterState = {
    HIDDEN: 'hidden',
    EMPTY: 'empty', // No buttons
    DRAFT: 'draft',
    ANALYSIS_DIET: 'analysis_diet',
    ANALYSIS_KEEP: 'analysis_keep',
    PROFILE: 'profile'
};

const FooterModule = {
    el: {
        container: null,
        retryBtn: null,
        adviceBtn: null,
        saveBtn: null,
    },

    init() {
        this.el.container = document.getElementById('result-footer');
        this.el.retryBtn = document.getElementById('re-analyze-btn');
        this.el.adviceBtn = document.getElementById('update-advice-btn');
        this.el.saveBtn = document.getElementById('save-btn');

        // Initial state
        if (this.el.container) this.el.container.classList.add('hidden');
    },

    /**
     * Update footer state
     * @param {string} state - One of FooterState
     * @param {object} context - Session object or other context
     */
    update(state, context) {
        if (!this.el.container) return;

        // Reset visibility first to ensure clean state
        this._toggle(this.el.retryBtn, false);
        this._toggle(this.el.adviceBtn, false);
        this._toggle(this.el.saveBtn, false);

        if (state === FooterState.HIDDEN || state === FooterState.EMPTY) {
            this.el.container.classList.add('hidden');
            return;
        }

        this.el.container.classList.remove('hidden');

        switch (state) {
            case FooterState.DRAFT:
                this._renderDraftMode(context);
                break;
            case FooterState.ANALYSIS_DIET:
                this._renderDietMode(context);
                break;
            case FooterState.ANALYSIS_KEEP:
                this._renderKeepMode(context);
                break;
            case FooterState.PROFILE:
                this._renderProfileMode(context);
                break;
        }
    },

    _renderDraftMode(session) {
        // Only show 'Start Analysis' (using the save button slot)
        this._setupButton(this.el.saveBtn, {
            visible: true,
            text: '开始分析',
            icon: 'bookmark', // sparkle icon
            type: 'primary',
            disabled: false,
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                if (window.Dashboard && typeof window.Dashboard.retryDraft === 'function') {
                    window.Dashboard.retryDraft(session.id);
                }
            }
        });
    },

    _renderDietMode(session) {
        // 1. Retry
        this._setupButton(this.el.retryBtn, {
            visible: true,
            text: '重新分析',
            icon: 'refresh',
            type: 'secondary',
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                if (window.Dashboard && typeof window.Dashboard.reAnalyze === 'function') {
                    window.Dashboard.reAnalyze();
                }
            }
        });

        // 2. Advice
        this._setupButton(this.el.adviceBtn, {
            visible: true,
            text: '更新建议',
            icon: 'update',
            type: 'secondary',
            disabled: false, // Could add loading state check here
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                if (window.Dashboard && typeof window.Dashboard.updateAdvice === 'function') {
                    window.Dashboard.updateAdvice();
                }
            }
        });

        // 3. Save
        const isSaved = session.isSaved;
        // Check data change
        let isModified = false;
        if (window.Dashboard && typeof window.Dashboard.isDataUnchanged === 'function') {
            isModified = !window.Dashboard.isDataUnchanged(session);
        }

        let saveConfig = {
            visible: true,
            type: 'primary',
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                window.Dashboard.saveCard();
            }
        };

        if (isSaved && !isModified) {
            saveConfig.text = '已保存';
            saveConfig.icon = 'check';
            saveConfig.disabled = true;
        } else if (isSaved && isModified) {
            saveConfig.text = '更新记录';
            saveConfig.icon = 'save';
            saveConfig.disabled = false;
        } else {
            saveConfig.text = '保存记录';
            saveConfig.icon = 'save';
            saveConfig.disabled = false;
        }

        this._setupButton(this.el.saveBtn, saveConfig);
    },

    _renderProfileMode(context) {
        // Profile has 3 actions: Revert All, Back, Save Profile
        // We need to map them to the 3 available slots: Retry(Revert), Advice(Back), Save(Save)

        // 1. Revert (Mapped to Retry Btn Slot)
        const hasChanges = window.ProfileModule ? window.ProfileModule.hasChanges() : false;

        this._setupButton(this.el.retryBtn, {
            visible: hasChanges,
            text: '↩ 还原全部',
            icon: null,
            type: 'ghost',
            onClick: () => {
                if (window.ProfileRenderModule) window.ProfileRenderModule.revertAll();
            }
        });

        // 2. Back (Mapped to Advice Btn Slot)
        this._setupButton(this.el.adviceBtn, {
            visible: true,
            text: '返回',
            icon: null,
            type: 'secondary',
            onClick: () => {
                if (window.Dashboard) window.Dashboard.switchView('analysis');
            }
        });

        // 3. Save (Mapped to Save Btn Slot)
        this._setupButton(this.el.saveBtn, {
            visible: true,
            text: '保存档案',
            icon: 'save',
            type: 'primary',
            disabled: !hasChanges,
            onClick: () => {
                if (window.ProfileRenderModule) window.ProfileRenderModule.saveProfile();
            }
        });
    },

    _renderKeepMode(session) {
        // 1. Retry
        this._setupButton(this.el.retryBtn, {
            visible: true,
            text: '重新分析',
            icon: 'refresh',
            type: 'secondary',
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                if (window.Dashboard && typeof window.Dashboard.reAnalyze === 'function') {
                    window.Dashboard.reAnalyze();
                }
            }
        });

        // 2. Advice (Hidden for Keep)
        this._toggle(this.el.adviceBtn, false);

        // 3. Save
        let saveConfig = {
            visible: true,
            type: 'primary',
            text: session.isSaved ? '更新记录' : '保存记录',
            icon: 'save',
            onClick: () => {
                if (window.Dashboard?.checkDemoLimit()) return;
                window.Dashboard.saveCard();
            }
        };
        // Simple saved check
        if (session.isSaved) {
            saveConfig.text = '已保存';
            saveConfig.icon = 'check';
            saveConfig.disabled = true;
        }

        this._setupButton(this.el.saveBtn, saveConfig);
    },

    _toggle(el, visible) {
        if (!el) return;
        if (visible) el.style.display = '';
        else el.style.display = 'none';
    },

    _setupButton(el, config) {
        if (!el) return;
        this._toggle(el, config.visible);

        if (config.visible) {
            // Text & Icon
            const iconHtml = (window.IconManager && config.icon)
                ? window.IconManager.render(config.icon)
                : '';
            el.innerHTML = `${iconHtml} ${config.text}`;

            // Class (Primary/Secondary)
            el.className = `btn btn-${config.type}`;

            // Disabled
            el.disabled = Boolean(config.disabled);

            // Handler - Remove old listeners (cloning node is a brute force way, or use a property to store handler)
            // Using onclick property is safest for replacement here
            el.onclick = config.onClick;
        }
    }
};

window.FooterModule = FooterModule;
window.FooterState = FooterState;
