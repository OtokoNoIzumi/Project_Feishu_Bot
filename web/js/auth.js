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

        const getLogTime = () => {
            const now = new Date();
            const pad = (n) => n.toString().padStart(2, '0');
            return `[AI_second_me ${pad(now.getMonth() + 1)}/${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}]`;
        };

        console.log(`${getLogTime()} [Auth] init started`);

        try {
            // 等待 Clerk SDK 脚本加载完成
            console.log(`${getLogTime()} [Auth] waiting for Clerk SDK...`);
            await this.waitForClerk();
            console.log(`${getLogTime()} [Auth] Clerk SDK found. Starting load()...`);

            // 异步加载 Clerk，不阻断主流程
            window.Clerk.load().then(() => {
                const initTime = getLogTime();
                console.log(`${initTime} [Auth] window.Clerk.load() completed`);

                this.initialized = true;
                this.user = window.Clerk.user;

                // 触发延迟的回调
                if (this._onInitCallbacks) {
                    console.log(`${initTime} [Auth] Triggering ${this._onInitCallbacks.length} callbacks`);
                    this._onInitCallbacks.forEach(cb => cb());
                    this._onInitCallbacks = [];
                }

                // 监听认证状态变化
                window.Clerk.addListener((resources) => {
                    this.user = resources.user;
                    this.onAuthStateChange(resources);
                });

                console.log(`${initTime} [Auth] Clerk fully initialized asynchronously`);
            }).catch(err => {
                console.error('[Auth] Failed to load Clerk:', err);
            });

        } catch (error) {
            console.error('[Auth] Failed to wait for Clerk SDK:', error);
        }
    },

    // 增加一个注册初始化回调的方法
    onInit(callback) {
        if (this.initialized) {
            callback();
        } else {
            if (!this._onInitCallbacks) this._onInitCallbacks = [];
            this._onInitCallbacks.push(callback);
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
     * 检查是否为演示模式 (URL param: demo=true)
     */
    isDemoMode() {
        if (typeof window === 'undefined') return false;
        const params = new URLSearchParams(window.location.search);
        return params.get('demo') === 'true';
    },

    /**
     * 保护路由 - 未登录时跳转到登录页
     */
    requireAuth() {
        // [Demo Mode Bypass]
        if (this.isDemoMode()) {
            console.log('[Auth] Running in Demo Mode. Login check bypassed.');
            return true;
        }

        if (!this.isSignedIn()) {
            window.location.href = '/web/index.html';
            return false;
        }
        return true;
    },
};
