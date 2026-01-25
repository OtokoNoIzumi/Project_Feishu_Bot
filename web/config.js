/**
 * 前端配置文件
 * 
 * 环境自动检测：根据 hostname 自动选择 API 地址和 Clerk Key
 * - localhost/127.0.0.1 → 本地开发环境 (Test)
 * - 其他域名 → 生产环境 (Live)
 */

const IS_LOCAL = window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1';

const CONFIG = {
    // 环境标识 (用于日志和调试)
    ENV: IS_LOCAL ? 'development' : 'production',

    // Clerk 公钥（可以公开）
    CLERK_PUBLISHABLE_KEY: IS_LOCAL
        ? 'pk_test_YWR2YW5jZWQtcHVtYS01Mi5jbGVyay5hY2NvdW50cy5kZXYk'  // Test Instance
        : 'pk_live_Y2xlcmsuaXp1bWlsaWZlLnNpdGUk',                      // Live Instance

    // 后端 API 地址
    API_BASE_URL: IS_LOCAL
        ? 'http://127.0.0.1:7701/api'           // 本地后端
        : 'https://izumiai.site:7701/api',      // 生产后端

    // 应用名称
    APP_NAME: 'Diet & Keep Analyzer',
};

// 启动时输出当前环境 (方便调试)
console.log(`[Config] Running in ${CONFIG.ENV} mode | API: ${CONFIG.API_BASE_URL}`);

// 防止意外修改
Object.freeze(CONFIG);
