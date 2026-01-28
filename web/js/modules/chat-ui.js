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
        for (const file of images) {
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
    }
};

window.ChatUIModule = ChatUIModule;
