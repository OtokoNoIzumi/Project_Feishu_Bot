/**
 * ErrorHandler 模块
 * 
 * 负责统一与模块化的错误信息映射，将后端错误代码/消息转换为
 * 用户友好的提示，支持未来扩展多语言。
 */

const ErrorHandlerModule = {
    // 错误代码映射表
    errors: {
        'DAILY_LIMIT_REACHED': {
            title: '今日次数已用完',
            message: '每日分析次数已耗尽 ({current}/{limit})。请升级会员继续使用。',
            action: 'profile_code', // 指向激活码输入
            level: 'warning'
        },
        'SUBSCRIPTION_EXPIRED': {
            title: '订阅已过期',
            message: '您的订阅已过期，请续费后继续使用。',
            action: 'profile_code',
            level: 'warning'
        },
        '503': {
            title: '服务繁忙',
            message: 'AI 服务暂时拥堵，请稍后重试 (503)。',
            action: 'retry',
            level: 'error'
        },
        '429': {
            title: '操作过于频繁',
            message: '请求过于频繁，请休息一下再试。',
            action: 'retry',
            level: 'warning'
        },
        'NETWORK_ERROR': {
            title: '网络错误',
            message: '网络连接异常，请检查您的网络设置。',
            action: 'retry',
            level: 'error'
        },
        // Stream Specific Errors
        'ERR_MODEL_BUSY': {
            title: '服务繁忙',
            message: 'AI 模型繁忙 (503)，请稍后重试。',
            action: 'retry',
            level: 'error'
        },
        'ERR_QUOTA_EXCEEDED': {
            title: '额度不足',
            message: 'API 额度不足 (429)，请稍后重试。',
            action: 'retry',
            level: 'error'
        },
        'ERR_SAFETY_BLOCK': {
            title: '内容拦截',
            message: '生成内容被安全策略拦截，请尝试调整输入。',
            action: 'retry',
            level: 'warning'
        },
        'ERR_STREAM_UNKNOWN': {
            title: '生成中断',
            message: '生成过程中断，请重试。',
            action: 'retry',
            level: 'error'
        },
        'DEFAULT': {
            title: '分析失败',
            message: '遇到未知错误：{msg}',
            action: 'retry',
            level: 'error'
        }
    },

    /**
     * 获取格式化的错误信息
     * @param {object|string} error - 错误对象或字符串
     * @returns {object} { title, message, action, level }
     */
    getFriendlyError(error) {
        let code = 'DEFAULT';
        let msg = typeof error === 'string' ? error : (error.message || 'Unknown error');
        let metadata = {};

        // 0. 尝试直接匹配 Error Code (用于流式错误码等)
        if (typeof error === 'string' && this.errors[error]) {
            code = error;
        }
        // 1. 尝试从结构化 APIError 中提取
        else if (error && error.data && error.data.detail) {
            if (error.data.detail.code) code = error.data.detail.code;
            if (error.data.detail.metadata) metadata = error.data.detail.metadata;
        }
        // 2. 尝试从错误消息字符串匹配常见 HTTP 错误
        else if (msg.includes('503')) {
            code = '503';
        } else if (msg.includes('429')) {
            code = '429';
        } else if (msg.toLowerCase().includes('network')) {
            code = 'NETWORK_ERROR';
        }

        // 3. 获取配置
        let config = this.errors[code] || this.errors['DEFAULT'];

        // 4. 格式化消息 (替换占位符)
        let formattedMsg = config.message;
        if (code === 'DAILY_LIMIT_REACHED' && metadata.limit) {
            formattedMsg = formattedMsg.replace('{limit}', metadata.limit).replace('{current}', metadata.limit);
        } else if (code === 'DEFAULT') {
            formattedMsg = formattedMsg.replace('{msg}', msg);
        }

        return {
            title: config.title,
            message: formattedMsg,
            action: config.action,
            level: config.level,
            originalError: error
        };
    }
};

window.ErrorHandlerModule = ErrorHandlerModule;
