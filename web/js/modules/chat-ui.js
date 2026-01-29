/**
 * Chat UI Logic Module
 * 
 * 负责聊天区域的交互逻辑：
 * - 消息渲染 (addMessage)
 * - 图片预览与上传处理 (handleFiles, renderPreviews)
 * - 发送按钮状态更新
 * 
 * 挂载到 Dashboard 实例运行
 */
const ChatUIModule = {

    // ========== 图片处理 ==========

    async handleFiles(files) {
        const images = Array.from(files).filter(f => f.type.startsWith('image/'));
        const MAX_BATCH = 10;
        const WARN_THRESHOLD = 9;

        for (const file of images) {
            if (this.pendingImages.length >= MAX_BATCH) {
                if (window.ToastUtils) {
                    ToastUtils.show(`单次最多仅支持 ${MAX_BATCH} 张图片`, 'warning');
                } else {
                    console.warn(`[ChatUI] Max batch size reached: ${MAX_BATCH}`);
                }
                break;
            }

            // Quality warning at threshold
            if (this.pendingImages.length === WARN_THRESHOLD - 1) {
                if (window.ToastUtils) {
                    ToastUtils.show('图片过多可能会产生识别错误，建议单次控制在 9 张以内', 'info', 4000);
                }
            }

            // 依赖 Dashboard 上的 fileToBase64 代理
            const base64 = await this.fileToBase64(file);
            this.pendingImages.push({
                file,
                base64,
                preview: URL.createObjectURL(file)
            });
        }
        this.renderPreviews();
        this.updateSendButton();
    },

    renderPreviews() {
        const container = this.el.previewContainer;
        if (!container) return;

        if (this.pendingImages.length === 0) {
            container.classList.add('hidden');
            container.innerHTML = '';
            return;
        }

        container.classList.remove('hidden');
        container.innerHTML = this.pendingImages.map((img, i) => `
      <div class="preview-item">
        <img src="${img.preview}" alt="Preview">
        <button class="preview-remove" onclick="Dashboard.removeImage(${i})">×</button>
      </div>
    `).join('');
    },

    removeImage(index) {
        if (this.pendingImages[index]) {
            URL.revokeObjectURL(this.pendingImages[index].preview);
            this.pendingImages.splice(index, 1);
            this.renderPreviews();
            this.updateSendButton();
        }
    },

    updateSendButton() {
        if (!this.el.sendBtn) return;
        const hasContent = this.pendingImages.length > 0 || this.el.chatInput?.value.trim();
        this.el.sendBtn.disabled = !hasContent;
    },

    // ========== 消息显示 ==========

    addMessage(content, role, options = {}) {
        if (options.sessionId) {
            options.onClick = (id) => this.selectSession(id);
        }
        // SessionModule.renderMessage 是核心静态方法
        return SessionModule.renderMessage(this.el.chatMessages, content, role, options);
    },

    updateLimitStatus(info) {
        const container = document.getElementById('limit-status-container');
        if (!container || !info) return;

        const { usage, max } = info;
        const app = window.Dashboard;

        // Determine feature based on current view/mode
        let feature = 'analyze';
        let label = '分析';
        if (app.view === 'profile') {
            feature = 'profile';
            label = '目标沟通';
        } else if (app.mode === 'advice') {
            feature = 'advice';
            label = '顾问讨论';
        }

        const used = usage[feature] || 0;
        const limit = max[feature] || 0;

        let text = '';
        let title = '';
        let isLimitReached = false;

        if (limit === -1) {
            text = `${used}`;
            title = `今日${label} (已用)`;
        } else {
            const remaining = Math.max(0, limit - used);
            text = `${remaining}`;
            title = `今日${label}剩余`;
            isLimitReached = remaining === 0;
        }

        const imgUsed = usage.image_analyze || 0;
        const imgLimit = max.image_analyze || 0;

        let imgText = '';
        let imgTitle = '';
        let isImgLimitReached = false;

        if (imgLimit === -1) {
            imgText = `${imgUsed}`;
            imgTitle = '今日图片分析 (已用)';
        } else {
            const imgRemaining = Math.max(0, imgLimit - imgUsed);
            imgText = `${imgRemaining}`;
            imgTitle = '今日图片分析剩余';
            isImgLimitReached = imgRemaining === 0;
        }

        container.classList.remove('hidden');
        container.innerHTML = `
            <div class="limit-status-item ${isLimitReached ? 'limit-reached' : ''}" title="${title}">
                <span class="limit-icon">💬</span> ${text}
            </div>
            <div class="limit-status-item ${isImgLimitReached ? 'limit-reached' : ''}" title="${imgTitle}">
                <span class="limit-icon">📷</span> ${imgText}
            </div>
        `;
    }
};

window.ChatUIModule = ChatUIModule;
