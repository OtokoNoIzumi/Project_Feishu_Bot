/**
 * Clerk 认证模块
 * 处理用户登录、登出和状态管理
 */

const Auth = {
    // 当前用户信息
    user: null,

    // 是否已初始化
    initialized: false,

    /**
     * 初始化 Clerk
     * 必须在 Clerk SDK 加载完成后调用
     */
    async init() {
        if (this.initialized) return;

        try {
            // 等待 Clerk SDK 脚本加载完成
            await this.waitForClerk();

            // 等待 Clerk 加载完成
            await window.Clerk.load();
            this.initialized = true;

            // 监听认证状态变化
            window.Clerk.addListener((resources) => {
                this.user = resources.user;
                this.onAuthStateChange(resources);
            });

            // 设置初始用户状态
            this.user = window.Clerk.user;

            console.log('[Auth] Clerk initialized successfully');
        } catch (error) {
            console.error('[Auth] Failed to initialize Clerk:', error);
            throw error;
        }
    },

    /**
     * 等待 Clerk SDK 脚本加载
     */
    waitForClerk() {
        return new Promise((resolve, reject) => {
            if (window.Clerk) {
                resolve();
                return;
            }
            let attempts = 0;
            const interval = setInterval(() => {
                attempts++;
                if (window.Clerk) {
                    clearInterval(interval);
                    resolve();
                } else if (attempts >= 50) {
                    clearInterval(interval);
                    reject(new Error('Clerk SDK load timeout'));
                }
            }, 100);
        });
    },

    /**
     * 认证状态变化回调
     * 子页面可以覆盖此方法
     */
    onAuthStateChange(resources) {
        console.log('[Auth] State changed:', resources.user ? 'logged in' : 'logged out');
    },

    /**
     * 检查是否已登录
     */
    isSignedIn() {
        return !!window.Clerk?.user;
    },

    /**
     * 获取当前用户
     */
    getUser() {
        return window.Clerk?.user || null;
    },

    /**
     * 获取用户 ID
     */
    getUserId() {
        return window.Clerk?.user?.id || null;
    },

    /**
     * 获取 Session Token (用于调用后端 API)
     */
    async getToken() {
        if (!this.isSignedIn()) {
            throw new Error('User is not signed in');
        }
        return await window.Clerk.session.getToken();
    },

    /**
     * 打开登录弹窗
     */
    openSignIn() {
        window.Clerk.openSignIn();
    },

    /**
     * 打开注册弹窗
     */
    openSignUp() {
        window.Clerk.openSignUp();
    },

    /**
     * 登出
     */
    async signOut() {
        await window.Clerk.signOut();
        // 跳转到登录页
        window.location.href = '/web/index.html';
    },

    /**
     * 渲染用户按钮 (头像 + 下拉菜单)
     * @param {string|HTMLElement} container - 容器元素或选择器
     */
    mountUserButton(container) {
        const el = typeof container === 'string'
            ? document.querySelector(container)
            : container;

        if (el && window.Clerk) {
            window.Clerk.mountUserButton(el);
        }
    },

    /**
     * 渲染登录组件
     * @param {string|HTMLElement} container - 容器元素或选择器
     */
    mountSignIn(container) {
        const el = typeof container === 'string'
            ? document.querySelector(container)
            : container;

        if (el && window.Clerk) {
            window.Clerk.mountSignIn(el, {
                routing: 'hash',
                signUpUrl: '#/sign-up',
            });
        }
    },

    /**
     * 渲染注册组件
     * @param {string|HTMLElement} container - 容器元素或选择器
     */
    mountSignUp(container) {
        const el = typeof container === 'string'
            ? document.querySelector(container)
            : container;

        if (el && window.Clerk) {
            window.Clerk.mountSignUp(el, {
                routing: 'hash',
                signInUrl: '#/sign-in',
            });
        }
    },

    /**
     * 保护路由 - 未登录时跳转到登录页
     */
    requireAuth() {
        if (!this.isSignedIn()) {
            window.location.href = '/web/index.html';
            return false;
        }
        return true;
    },
};
