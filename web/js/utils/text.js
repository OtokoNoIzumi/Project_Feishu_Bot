/**
 * 文本处理工具函数
 * 
 * 包含 Markdown 转换等纯文本操作
 */

const TextUtils = {
    // 使用 marked 库转换 Markdown
    simpleMarkdownToHtml(text) {
        if (!text) return '';
        if (typeof marked === 'undefined') {
            console.error('marked.js is not loaded!');
            return text;
        }
        // 配置 marked 处理换行 (gfm: true, breaks: true)
        return marked.parse(text, { breaks: true });
    },
};

// 挂载到全局
window.TextUtils = TextUtils;
