/**
 * Dashboard UI Logic Module
 * 
 * 负责 Dashboard 的纯 UI 交互逻辑：
 * - 缓存 DOM 元素
 * - 事件绑定 (不包括 Session 内部逻辑)
 * - 视图切换 (Panel/Profile/Mode)
 * - 状态提示 (Loading/Error/Status)
 * 
 * 挂载到 Dashboard 实例运行
 */
const DashboardUIModule = {
    cacheElements() {
        this.el = {
            chatMessages: document.getElementById('chat-messages'),
            chatInput: document.getElementById('chat-input'),
            sendBtn: document.getElementById('send-btn'),
            uploadBtn: document.getElementById('upload-btn'),
            fileInput: document.getElementById('file-input'),
            inputBox: document.getElementById('input-box'),
            previewContainer: document.getElementById('preview-container'),
            resultContent: document.getElementById('result-content'),
            resultStatus: document.getElementById('result-status'),
            resultTitle: document.getElementById('result-title'),
            resultFooter: document.getElementById('result-footer'),
            historyList: document.getElementById('history-list'),
            sideMenu: document.getElementById('side-menu'),
            toggleResultBtn: document.getElementById('toggle-result-btn'),
            openProfileBtn: document.getElementById('open-profile-btn'),
            resultCloseBtn: document.getElementById('result-close-btn'),
            resultOverlay: document.getElementById('result-overlay'),
        };
    },

    bindEvents() {
        // 左侧菜单：分析 / Profile
        this.el.sideMenu?.querySelectorAll('.side-menu-item')?.forEach(btn => {
            btn.addEventListener('click', () => this.switchView(btn.dataset.view));
        });

        // 模式切换
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchMode(btn.dataset.mode));
        });

        // 移动端：打开/折叠确认面板
        this.el.toggleResultBtn?.addEventListener('click', () => {
            this.setResultPanelOpen(!this.isResultPanelOpen);
        });
        this.el.resultCloseBtn?.addEventListener('click', () => this.setResultPanelOpen(false));
        this.el.resultOverlay?.addEventListener('click', () => this.setResultPanelOpen(false));

        // 移动端快捷入口：Profile
        this.el.openProfileBtn?.addEventListener('click', () => this.switchView('profile'));

        // 上传
        this.el.uploadBtn?.addEventListener('click', () => this.el.fileInput?.click());
        this.el.fileInput?.addEventListener('change', e => this.handleFiles(e.target.files));

        // 拖拽
        this.el.inputBox?.addEventListener('dragover', e => {
            e.preventDefault();
            this.el.inputBox.classList.add('dragover');
        });
        this.el.inputBox?.addEventListener('dragleave', () => {
            this.el.inputBox.classList.remove('dragover');
        });
        this.el.inputBox?.addEventListener('drop', e => {
            e.preventDefault();
            this.el.inputBox.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });

        // 输入
        this.el.chatInput?.addEventListener('input', () => this.updateSendButton());
        this.el.chatInput?.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.startNewAnalysis();
            }
        });

        // 粘贴 (Paste) support for images
        this.el.chatInput?.addEventListener('paste', e => {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            const files = [];
            for (let i = 0; i < items.length; i++) {
                if (items[i].kind === 'file' && items[i].type.startsWith('image/')) {
                    const file = items[i].getAsFile();
                    if (file) files.push(file);
                }
            }
            if (files.length > 0) {
                e.preventDefault();
                this.handleFiles(files);

                // Manually paste text if mixed content
                const text = (e.clipboardData || e.originalEvent.clipboardData).getData('text');
                if (text) {
                    const input = this.el.chatInput;
                    const start = input.selectionStart;
                    const end = input.selectionEnd;
                    const val = input.value;
                    input.value = val.substring(0, start) + text + val.substring(end);
                    input.selectionStart = input.selectionEnd = start + text.length;
                    this.updateSendButton();
                }
            }
        });

        // 发送（新建分析）
        this.el.sendBtn?.addEventListener('click', () => this.startNewAnalysis());

        // NOTE: reAnalyzeBtn, updateAdviceBtn, saveBtn 的事件由 FooterModule 统一管理

        // 初始化 Profile
        this.profile = this.loadProfile();
    },

    switchMode(mode) {
        this.mode = mode;
        // this.currentDialogueId = null; // Do NOT clear dialogue ID on mode switch to allow context resume
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });

        // Refresh limit display
        if (window.ChatUIModule && window.ProfileModule && ProfileModule.limitsInfo) {
            ChatUIModule.updateLimitStatus(ProfileModule.limitsInfo);
        }
    },

    isMobile() {
        return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
    },

    setResultPanelOpen(open) {
        this.isResultPanelOpen = Boolean(open);
        const panel = document.querySelector('.result-panel');
        if (panel) {
            panel.classList.toggle('mobile-open', this.isResultPanelOpen && this.isMobile());
        }
        if (this.el.resultOverlay) {
            this.el.resultOverlay.classList.toggle('hidden', !(this.isResultPanelOpen && this.isMobile()));
        }
    },

    switchView(view) {
        // 确保 Auth 已初始化
        if (!Auth.isSignedIn()) {
            console.warn('[Dashboard] Auth not ready, but allowing view switch to show status');
        }

        const next = view === 'profile' ? 'profile' : 'analysis';
        const prev = this.view;
        this.view = next;

        // [Fix] Always refresh Demo Mask text immediately after view change
        if (Auth.isDemoMode()) {
            this.renderDemoMask();
        }

        // Refresh limit display
        if (window.ChatUIModule && window.ProfileModule && ProfileModule.limitsInfo) {
            ChatUIModule.updateLimitStatus(ProfileModule.limitsInfo);
        }

        // 左侧菜单高亮
        this.el.sideMenu?.querySelectorAll('.side-menu-item')?.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === next);
        });

        // 聊天模式切换
        const modeSwitch = document.querySelector('.mode-switch');
        if (next === 'profile') {
            // Profile 模式：隐藏 diet/keep 切换，显示"档案沟通"
            if (modeSwitch) {
                this._savedModeSwitch = modeSwitch.innerHTML;
                this._savedMode = this.mode; // Save current mode
                modeSwitch.innerHTML = '<button class="mode-btn active" style="cursor: default; pointer-events: none;">档案沟通</button>';
            }
            this.renderProfileView();
            if (this.isMobile()) this.setResultPanelOpen(true);
            return;
        }

        // 切出 Profile 模式：还原聊天窗口状态
        if (prev === 'profile' && modeSwitch && this._savedModeSwitch) {
            modeSwitch.innerHTML = this._savedModeSwitch;
            this.bindModeSwitch(); // 重新绑定事件
            this.mode = this._savedMode || 'diet'; // Restore mode
        }

        // 回到分析视图
        if (this.currentSession && this.currentSession.versions.length > 0) {
            this.renderResult(this.currentSession);
        } else {
            // 如果没有 Session 但有 Dialogue ID，尝试重新加载对话 state (修复 Profile 回来消失的问题)
            if (this.currentDialogueId && !this.currentSession) {
                this.loadDialogue(this.currentDialogueId);
            } else {
                this.clearResult();
            }
        }
        // 刷新 Sidebar 标题 (确保单位变更实时生效)
        if (window.SidebarModule) {
            window.SidebarModule.render();
        }
        // 刷新所有会话卡片标题（确保能量单位等设置生效）
        this.sessions.forEach(s => this.updateSessionCard(s));
        if (this.isMobile()) this.setResultPanelOpen(true);

        // [Demo Mode] Re-render mask to update text if needed
        if (Auth.isDemoMode()) {
            this.renderDemoMask();
        }
    },

    bindModeSwitch() {
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.mode = btn.dataset.mode;
            });
        });
    },

    // ========== UI 状态反馈 ==========

    showLoading() {
        // 仅状态提示：不遮挡/不替换整个确认面板内容
        this.updateStatus('loading');
        if (window.FooterModule) {
            window.FooterModule.update(FooterState.HIDDEN);
        } else if (this.el.resultFooter) {
            this.el.resultFooter.classList.add('hidden');
        }
    },

    showError(error) {
        this.updateStatus('');
        const errorInfo = window.ErrorHandlerModule
            ? window.ErrorHandlerModule.getFriendlyError(error)
            : { title: '分析失败', message: (error.message || error || '未知错误') };

        // 默认展示逻辑：只要存在当前会话，就认为是分析流错误，回到 Draft 态展示错误横幅
        if (this.currentSession && typeof this.renderDraftState === 'function') {
            this.currentSession.lastError = errorInfo;
            this.renderDraftState(this.currentSession);
            return;
        }

        // 兜底：无活跃会话时的简洁提示
        if (window.ToastUtils) {
            ToastUtils.show(`${errorInfo.title}: ${errorInfo.message}`, 'error');
        }

        this.el.resultContent.innerHTML = `
      <div class="empty-state">
        <div style="font-size:1.5rem; margin-bottom:12px;">⚠️</div>
        <p class="text-error" style="font-weight:650;">${errorInfo.title}</p>
        <p style="font-size:0.9rem; color:var(--color-text-secondary);">${errorInfo.message}</p>
      </div>
    `;

        if (window.FooterModule) {
            window.FooterModule.update(FooterState.HIDDEN);
        }
    },

    clearResult() {
        // 轻量占位：不做大面积遮挡
        this.el.resultContent.innerHTML = `
      <div class="result-card" style="padding: 16px;">
        <div class="text-secondary" style="font-weight: 600; margin-bottom: 6px;">分析面板</div>
        <div class="text-muted" style="font-size: 0.875rem;">
          上传图片或输入描述后点击发送开始分析。分析过程中这里会显示状态与可编辑结果。
        </div>
      </div>
    `;
        if (window.FooterModule) {
            window.FooterModule.update(FooterState.HIDDEN); // Or EMPTY
        } else if (this.el.resultFooter) {
            this.el.resultFooter.classList.add('hidden');
        }
        this.el.resultTitle.textContent = '分析结果';
        this.updateStatus('');
    },

    updateStatus(status) {
        // Toggle loading class on result content for animations
        if (this.el.resultContent) {
            this.el.resultContent.classList.toggle('is-loading', status === 'loading');
        }

        const el = this.el.resultStatus;
        if (!el) return;
        el.className = 'result-status';
        if (status === 'saved') {
            el.textContent = '✓ 已保存';
            el.classList.add('saved');
        } else if (status === 'loading') {
            el.innerHTML = `<span class="loading-spinner" style="display:inline-block; width:14px; height:14px; vertical-align: -2px; margin-right:6px;"></span>分析中...`;
            el.classList.add('loading');
        } else if (status === 'modified') {
            el.textContent = '● 已修改';
            el.classList.add('modified');
        } else {
            el.textContent = '';
        }
    },

    updateButtonStates(session) {
        if (!window.FooterModule) return;

        if (!session) {
            window.FooterModule.update(FooterState.HIDDEN);
            return;
        }

        // Draft 状态特殊处理
        if (!session.versions || session.versions.length === 0) {
            window.FooterModule.update(FooterState.DRAFT, session);
            return;
        }

        // Determine mode
        if (session.mode === 'diet') {
            window.FooterModule.update(FooterState.ANALYSIS_DIET, session);
        } else {
            window.FooterModule.update(FooterState.ANALYSIS_KEEP, session);
        }
    }
};

window.DashboardUIModule = DashboardUIModule;
