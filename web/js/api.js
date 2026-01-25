/**
 * API 通信模块
 * 与 FastAPI 后端交互
 */

const API = {
    /**
     * 发送 API 请求
     * @param {string} endpoint - API 端点 (如 '/diet/analyze')
     * @param {object} options - fetch 选项
     * @returns {Promise<object>} - 响应数据
     */
    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_BASE_URL}${endpoint}`;

        // 构建请求头
        const headers = {
            ...options.headers,
        };

        // 如果有 JSON body，设置 Content-Type
        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }

        // 【核心改动】添加 X-User-ID Header
        const userId = Auth.getUserId() || 'anonymous';
        headers['X-User-ID'] = userId;

        // 如果用户已登录，添加 Authorization 头
        if (Auth.isSignedIn()) {
            try {
                const token = await Auth.getToken();
                headers['Authorization'] = `Bearer ${token}`;
            } catch (e) {
                console.warn('[API] Could not get auth token:', e);
            }
        }

        // 超时控制 (默认 150s)
        const timeout = options.timeout || 150000;
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        const startTime = Date.now();

        try {
            const response = await fetch(url, {
                ...options,
                headers,
                signal: controller.signal,
            });
            clearTimeout(id);

            // 记录耗时
            const duration = Date.now() - startTime;

            // 解析响应
            let data;
            let bodyText = "";
            try {
                bodyText = await response.text();
                data = JSON.parse(bodyText);
            } catch (jsonError) {
                console.warn('[API] Response is not valid JSON:', bodyText.substring(0, 200));
                // 如果不是 JSON，尝试包装一下或抛出
                if (response.ok) {
                    data = { message: "Success (Non-JSON response)", raw: bodyText };
                } else {
                    throw new APIError(`Invalid JSON Response: ${response.status}`, response.status, null);
                }
            }

            // 日志预览 (前100字符)
            const bodyPreview = bodyText.substring(0, 100).replace(/\n/g, ' ');

            if (response.ok) {
                if (duration > 5000) {
                    console.warn(`[API] Slow request: ${endpoint} took ${duration}ms | ${response.status} | ${bodyPreview}...`);
                } else {
                    console.log(`[API] Request: ${endpoint} took ${duration}ms | ${response.status} | ${bodyPreview}...`);
                }
                return data;
            } else {
                console.error(`[API] Error request: ${endpoint} | ${response.status} | ${bodyPreview}...`);
                // Handle structured error detail from backend
                let errorMessage = 'Request failed';
                if (data && typeof data.detail === 'object' && data.detail !== null) {
                    errorMessage = data.detail.message || data.detail.code || JSON.stringify(data.detail);
                } else if (data && data.detail) {
                    errorMessage = data.detail;
                } else if (data && data.error) {
                    errorMessage = data.error;
                }

                const error = new APIError(errorMessage, response.status, data);
                // Preserve structured detail for catch handlers
                error.response = { data };
                throw error;
            }
        } catch (error) {
            clearTimeout(id);
            if (error.name === 'AbortError') {
                throw new APIError(`请求超时 (${timeout / 1000}s)，请重试`, 408, null);
            }
            if (error instanceof APIError) throw error;
            throw new APIError(`Network error: ${error.message}`, 0, null);
        }
    },

    /**
     * GET 请求
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request(url, { method: 'GET' });
    },

    /**
     * POST 请求 (JSON)
     */
    async post(endpoint, data = {}, options = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
            ...options,
        });
    },

    /**
     * POST 请求 (FormData, 用于文件上传)
     */
    async postForm(endpoint, formData, options = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: formData,
            ...options,
        });
    },

    // ========== Diet API ==========

    /**
     * 饮食分析
     * @param {string} userNote - 用户备注
     * @param {string[]} imagesB64 - Base64 编码的图片数组
     * @param {boolean} autoSave - 是否自动保存
     */
    async analyzeDiet(userNote, imagesB64, autoSave = false) {
        // user_id 已移至 Header，body 不再包含
        // 将超时设置延长至 180s 以适应大图上传
        return this.post('/diet/analyze', {
            user_note: userNote,
            images_b64: imagesB64,
            auto_save: autoSave,
        }, { timeout: 150000 });
    },

    /**
     * 获取饮食建议
     * @param {object} facts - 饮食数据
     * @param {string} userNote - 用户说明
     */
    async getDietAdvice(facts, userNote = '') {
        return this.post('/diet/advice', {
            facts,
            user_note: userNote,
        });
    },

    /**
     * 保存饮食记录 (使用统一 storage API)
     * @param {object} data - 饮食记录数据
     */
    async saveDiet(data) {
        return this.post('/storage/diet/save', {
            meal_summary: data.meal_summary || {},
            dishes: data.dishes || [],
            captured_labels: data.captured_labels || [],
            image_hashes: data.image_hashes || [],
            record_id: data.record_id || null,
            occurred_at: data.occurred_at || null,
        });
    },

    /**
     * 获取饮食历史
     * @param {number} limit - 返回数量
     */
    async getDietHistory(limit = 20) {
        // user_id 已移至 Header，query 不再包含
        return this.get('/diet/history', { limit });
    },

    // ========== Keep API ==========

    /**
     * Keep 分析
     * @param {string} userNote - 用户备注
     * @param {string[]} imagesB64 - Base64 编码的图片数组
     * @param {boolean} autoSave - 是否自动保存
     */
    async analyzeKeep(userNote, imagesB64, autoSave = false) {
        // 将超时设置延长至 180s
        return this.post('/keep/analyze', {
            user_note: userNote,
            images_b64: imagesB64,
            auto_save: autoSave,
        }, { timeout: 150000 });
    },

    /**
     * 保存 Keep 记录 (使用统一 storage API)
     * @param {object} data - Keep 记录数据
     * @param {string} eventType - 事件类型 (scale/sleep/dimensions)
     */
    async saveKeep(data, eventType = 'scale') {
        return this.post('/storage/keep/save', {
            event_type: eventType,
            event_data: data,
            image_hashes: data.image_hashes || [],
            record_id: data.record_id || null,
        });
    },

    // ========== Profile API ==========

    /**
     * 获取用户 Profile（设置 + 动态指标）
     */
    async getProfile() {
        return this.get('/user/profile');
    },

    /**
     * 保存用户 Profile
     * @param {object} profile - Profile 数据
     */
    async saveProfile(profile) {
        return this.post('/user/profile', profile);
    },

    /**
     * Profile AI 分析
     * @param {string} userNote - 用户输入
     * @param {number} targetMonths - 目标月份（可选）
     * @param {boolean} autoSave - 是否自动保存
     * @param {object} profileOverride - 前端当前编辑的 Profile（优先使用）
     * @param {object} metricsOverride - 前端编辑的身高/体重
     */
    async analyzeProfile(userNote, targetMonths = null, autoSave = false, profileOverride = null, metricsOverride = null) {
        const data = {
            user_note: userNote,
            auto_save: autoSave,
        };
        if (targetMonths) {
            data.target_months = targetMonths;
        }
        if (profileOverride) {
            data.profile_override = profileOverride;
        }
        if (metricsOverride) {
            data.metrics_override = metricsOverride;
        }
        return this.post('/user/profile/analyze', data);
    },

    // ========== Dialogue API (MVP 2.1) ==========

    /**
     * 获取对话列表
     */
    async getDialogues(limit = 20, offset = 0) {
        return this.get('/dialogues', { limit, offset });
    },

    /**
     * 创建新对话
     * @param {string} title 
     */
    async createDialogue(title) {
        return this.post('/dialogues', { title });
    },

    /**
     * 获取对话详情
     */
    async getDialogue(id) {
        return this.get(`/dialogues/${id}`);
    },

    /**
     * 追加消息到对话
     */
    async appendMessage(dialogueId, message) {
        return this.request(`/dialogues/${dialogueId}/message`, {
            method: 'PATCH',
            body: JSON.stringify(message)
        });
    },

    /**
     * 更新对话消息
     */
    async updateMessage(dialogueId, message) {
        return this.request(`/dialogues/${dialogueId}/messages/${message.id}`, {
            method: 'PATCH',
            body: JSON.stringify(message)
        });
    },

    /**
     * 更新对话（如重命名）
     */
    async updateDialogue(dialogueId, title) {
        return this.request(`/dialogues/${dialogueId}`, {
            method: 'PATCH',
            body: JSON.stringify({ title })
        });
    },

    /**
     * 删除对话
     */
    async deleteDialogue(dialogueId) {
        return this.request(`/dialogues/${dialogueId}`, { method: 'DELETE' });
    },

    // ========== Result Card API (MVP 2.1) ==========

    /**
     * 获取卡片列表
     * @param {string} dialogueId (可选)
     */
    async getCards(dialogueId = null) {
        const params = {};
        if (dialogueId) params.dialogue_id = dialogueId;
        return this.get('/cards', params);
    },

    /**
     * 获取卡片详情
     */
    async getCard(cardId) {
        return this.get(`/cards/${cardId}`);
    },

    /**
     * 创建卡片 (分析完成后立即调用)
     */
    async createCard(cardData) {
        return this.post('/cards', cardData);
    },

    /**
     * 更新卡片状态/内容
     */
    async updateCard(cardId, cardData) {
        return this.request(`/cards/${cardId}`, {
            method: 'PATCH',
            body: JSON.stringify(cardData)
        });
    },
};

/**
 * 自定义 API 错误类
 */
class APIError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }
}
