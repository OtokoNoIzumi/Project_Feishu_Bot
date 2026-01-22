/**
 * 前端配置文件
 * 注意：CLERK_PUBLISHABLE_KEY 是公开的，可以安全地放在前端代码中
 */

const CONFIG = {
    // Clerk 公钥（可以公开）
    CLERK_PUBLISHABLE_KEY: 'pk_test_YWR2YW5jZWQtcHVtYS01Mi5jbGVyay5hY2NvdW50cy5kZXYk',

    // 后端 API 地址（需要根据实际部署情况修改）
    API_BASE_URL: 'https://izumiai.site:7701/api',
    // API_BASE_URL: 'http://127.0.0.1:7701/api',

    // 应用名称
    APP_NAME: 'Diet & Keep Analyzer',
};

// 防止意外修改
Object.freeze(CONFIG);
