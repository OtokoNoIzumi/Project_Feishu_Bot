/**
 * 主应用逻辑
 * Dashboard 页面的核心交互
 */

const App = {
    // 当前选中的图片 (Base64)
    selectedImages: [],

    // 上传的文件
    uploadedFiles: [],

    // 当前分析结果
    currentResult: null,

    // DOM 元素缓存
    elements: {},

    /**
     * 初始化应用
     */
    async init() {
        // 缓存 DOM 元素
        this.cacheElements();

        // 绑定事件
        this.bindEvents();

        // 初始化认证
        await Auth.init();

        // 检查登录状态
        if (!Auth.isSignedIn()) {
            window.location.href = '/web/index.html';
            return;
        }

        // 渲染用户按钮
        Auth.mountUserButton('#user-button');

        console.log('[App] Initialized');
    },

    /**
     * 缓存 DOM 元素
     */
    cacheElements() {
        this.elements = {
            // Chat
            chatMessages: document.getElementById('chat-messages'),
            chatInput: document.getElementById('chat-input'),
            sendBtn: document.getElementById('send-btn'),

            // Upload
            uploadZone: document.getElementById('upload-zone'),
            fileInput: document.getElementById('file-input'),
            previewGrid: document.getElementById('preview-grid'),

            // Actions
            analyzeBtn: document.getElementById('analyze-btn'),
            clearBtn: document.getElementById('clear-btn'),

            // Result
            resultContainer: document.getElementById('result-container'),

            // Mode selector
            modeSelect: document.getElementById('mode-select'),
        };
    },

    /**
     * 绑定事件
     */
    bindEvents() {
        const { uploadZone, fileInput, chatInput, sendBtn, analyzeBtn, clearBtn } = this.elements;

        // 上传区域 - 点击
        uploadZone?.addEventListener('click', () => fileInput?.click());

        // 上传区域 - 拖拽
        uploadZone?.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });

        uploadZone?.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });

        uploadZone?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });

        // 文件选择
        fileInput?.addEventListener('change', (e) => {
            this.handleFiles(e.target.files);
        });

        // 发送消息
        sendBtn?.addEventListener('click', () => this.sendMessage());
        chatInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // 分析按钮
        analyzeBtn?.addEventListener('click', () => this.analyze());

        // 清除按钮
        clearBtn?.addEventListener('click', () => this.clearImages());
    },

    /**
     * 处理上传的文件
     */
    async handleFiles(files) {
        const validFiles = Array.from(files).filter(f => f.type.startsWith('image/'));

        for (const file of validFiles) {
            // 转换为 Base64
            const base64 = await this.fileToBase64(file);
            this.selectedImages.push(base64);
            this.uploadedFiles.push(file);
        }

        this.renderPreviews();
        this.updateAnalyzeButton();
    },

    /**
     * 文件转 Base64
     */
    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                // 去掉 data:image/xxx;base64, 前缀
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    },

    /**
     * 渲染图片预览
     */
    renderPreviews() {
        const { previewGrid } = this.elements;
        if (!previewGrid) return;

        previewGrid.innerHTML = this.selectedImages.map((base64, index) => `
      <div class="preview-item">
        <img src="data:image/jpeg;base64,${base64}" alt="Preview ${index + 1}">
        <button class="preview-remove" onclick="App.removeImage(${index})">×</button>
      </div>
    `).join('');
    },

    /**
     * 移除图片
     */
    removeImage(index) {
        this.selectedImages.splice(index, 1);
        this.uploadedFiles.splice(index, 1);
        this.renderPreviews();
        this.updateAnalyzeButton();
    },

    /**
     * 清除所有图片
     */
    clearImages() {
        this.selectedImages = [];
        this.uploadedFiles = [];
        this.renderPreviews();
        this.updateAnalyzeButton();
    },

    /**
     * 更新分析按钮状态
     */
    updateAnalyzeButton() {
        const { analyzeBtn, chatInput } = this.elements;
        if (!analyzeBtn) return;

        const hasContent = this.selectedImages.length > 0 || chatInput?.value.trim();
        analyzeBtn.disabled = !hasContent;
    },

    /**
     * 发送聊天消息
     */
    sendMessage() {
        const { chatInput, chatMessages } = this.elements;
        const text = chatInput?.value.trim();
        if (!text) return;

        // 添加用户消息
        this.addMessage(text, 'user');
        chatInput.value = '';

        // 如果有图片，自动触发分析
        if (this.selectedImages.length > 0) {
            this.analyze();
        } else {
            // 否则显示提示
            this.addMessage('请上传食物图片进行分析，或者直接描述你的饮食内容。', 'assistant');
        }
    },

    /**
     * 添加聊天消息
     */
    addMessage(content, role) {
        const { chatMessages } = this.elements;
        if (!chatMessages) return;

        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;
        messageEl.textContent = content;
        chatMessages.appendChild(messageEl);

        // 滚动到底部
        chatMessages.scrollTop = chatMessages.scrollHeight;
    },

    /**
     * 执行分析
     */
    async analyze() {
        const { chatInput, analyzeBtn, resultContainer, modeSelect } = this.elements;
        const userNote = chatInput?.value.trim() || '';
        const mode = modeSelect?.value || 'diet';

        if (this.selectedImages.length === 0 && !userNote) {
            this.addMessage('请上传图片或输入描述后再分析。', 'assistant');
            return;
        }

        // 显示加载状态
        if (analyzeBtn) {
            analyzeBtn.disabled = true;
            analyzeBtn.innerHTML = '<span class="loading-spinner"></span> 分析中...';
        }

        if (resultContainer) {
            resultContainer.innerHTML = `
        <div class="result-card">
          <div class="skeleton" style="height: 20px; width: 60%; margin-bottom: 12px;"></div>
          <div class="skeleton" style="height: 16px; width: 80%; margin-bottom: 8px;"></div>
          <div class="skeleton" style="height: 16px; width: 70%;"></div>
        </div>
      `;
        }

        try {
            let result;

            if (mode === 'diet') {
                result = await API.analyzeDiet(userNote, this.selectedImages);
            } else {
                result = await API.analyzeKeep(userNote, this.selectedImages);
            }

            this.currentResult = result;
            this.renderResult(result, mode);

            // 添加成功消息
            this.addMessage(
                mode === 'diet'
                    ? '饮食分析完成！请在右侧查看详细结果。'
                    : 'Keep 数据分析完成！',
                'assistant'
            );

        } catch (error) {
            console.error('[App] Analysis failed:', error);
            this.addMessage(`分析失败: ${error.message}`, 'assistant');

            if (resultContainer) {
                resultContainer.innerHTML = `
          <div class="result-card" style="border-color: var(--color-error);">
            <div class="result-header">
              <div class="result-icon" style="background: var(--color-error);">⚠</div>
              <div>
                <div class="result-title">分析失败</div>
                <div class="result-subtitle">${error.message}</div>
              </div>
            </div>
          </div>
        `;
            }
        } finally {
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.innerHTML = '🔍 分析';
            }
        }
    },

    /**
     * 渲染分析结果
     */
    renderResult(result, mode) {
        const { resultContainer } = this.elements;
        if (!resultContainer) return;

        if (!result.success) {
            resultContainer.innerHTML = `
        <div class="result-card" style="border-color: var(--color-error);">
          <div class="result-title text-error">分析失败</div>
          <p>${result.error || '未知错误'}</p>
        </div>
      `;
            return;
        }

        const data = result.result || {};

        if (mode === 'diet') {
            this.renderDietResult(data);
        } else {
            this.renderKeepResult(data);
        }
    },

    /**
     * 渲染饮食分析结果
     */
    renderDietResult(data) {
        const { resultContainer } = this.elements;
        const summary = data.meal_summary || {};
        const dishes = data.dishes || [];

        let html = `
      <div class="result-card">
        <div class="result-header">
          <div class="result-icon">🍽️</div>
          <div>
            <div class="result-title">${summary.meal_name || '饮食分析'}</div>
            <div class="result-subtitle">${dishes.length} 种食物</div>
          </div>
        </div>
        
        <div style="margin-top: 16px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span class="text-secondary">总热量</span>
            <span style="font-weight: 600; color: var(--color-accent-primary);">
              ${summary.total_energy || 0} kcal
            </span>
          </div>
    `;

        // 添加营养素信息
        if (summary.total_protein) {
            html += `
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
          <span class="text-muted">蛋白质</span>
          <span>${summary.total_protein}g</span>
        </div>
      `;
        }
        if (summary.total_fat) {
            html += `
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
          <span class="text-muted">脂肪</span>
          <span>${summary.total_fat}g</span>
        </div>
      `;
        }
        if (summary.total_carb) {
            html += `
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
          <span class="text-muted">碳水</span>
          <span>${summary.total_carb}g</span>
        </div>
      `;
        }

        html += `</div>`;

        // 添加菜品列表
        if (dishes.length > 0) {
            html += `
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--color-border);">
          <div class="text-secondary" style="font-size: 0.75rem; margin-bottom: 8px;">食物明细</div>
      `;

            for (const dish of dishes) {
                html += `
          <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--color-border);">
            <span>${dish.name || '未知食物'}</span>
            <span class="text-secondary">${dish.estimated_energy || 0} kcal</span>
          </div>
        `;
            }

            html += `</div>`;
        }

        html += `
      </div>
      
      <button class="btn btn-primary btn-lg" style="width: 100%; margin-top: 16px;" onclick="App.saveResult()">
        💾 保存记录
      </button>
    `;

        resultContainer.innerHTML = html;
    },

    /**
     * 渲染 Keep 分析结果
     */
    renderKeepResult(data) {
        const { resultContainer } = this.elements;

        resultContainer.innerHTML = `
      <div class="result-card">
        <div class="result-header">
          <div class="result-icon">💪</div>
          <div>
            <div class="result-title">Keep 数据</div>
            <div class="result-subtitle">分析完成</div>
          </div>
        </div>
        <pre style="margin-top: 16px; font-size: 0.75rem; overflow: auto; max-height: 300px;">
${JSON.stringify(data, null, 2)}
        </pre>
      </div>
      
      <button class="btn btn-primary btn-lg" style="width: 100%; margin-top: 16px;" onclick="App.saveResult()">
        💾 保存记录
      </button>
    `;
    },

    /**
     * 保存分析结果
     */
    async saveResult() {
        if (!this.currentResult?.result) {
            this.addMessage('没有可保存的数据。', 'assistant');
            return;
        }

        try {
            const saved = await API.commitDiet(this.currentResult.result);
            this.addMessage('✅ 记录已保存！', 'assistant');

            // 清除当前数据
            this.clearImages();
            this.currentResult = null;
            this.elements.resultContainer.innerHTML = '';

        } catch (error) {
            console.error('[App] Save failed:', error);
            this.addMessage(`保存失败: ${error.message}`, 'assistant');
        }
    },
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => App.init());
