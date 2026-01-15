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

        // 超时控制 (默认 120s)
        const timeout = options.timeout || 120000;
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
            if (duration > 5000) {
                console.warn(`[API] Slow request: ${endpoint} took ${duration}ms`);
            } else {
                console.log(`[API] Request: ${endpoint} took ${duration}ms`);
            }

            // 解析响应
            const data = await response.json();

            if (!response.ok) {
                throw new APIError(
                    data.detail || data.error || 'Request failed',
                    response.status,
                    data
                );
            }

            return data;
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
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /**
     * POST 请求 (FormData, 用于文件上传)
     */
    async postForm(endpoint, formData) {
        return this.request(endpoint, {
            method: 'POST',
            body: formData,
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
        return this.post('/diet/analyze', {
            user_note: userNote,
            images_b64: imagesB64,
            auto_save: autoSave,
        });
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
        return this.post('/keep/analyze', {
            user_note: userNote,
            images_b64: imagesB64,
            auto_save: autoSave,
        });
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
