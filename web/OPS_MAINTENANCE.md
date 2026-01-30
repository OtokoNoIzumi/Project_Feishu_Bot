# 运维操作指南：域名迁移与环境配置

本文档记录了项目从 `.site` 域名迁移至 `.xyz` 域名的完整操作流程，以及相关的环境配置备忘。

---

## 1. 域名迁移背景
由于原域名 (`izumilife.site`) 被 Google Safe Browsing 误判封禁，且 `.site` 后缀信誉度较低，项目决定迁移至 `izumilife.xyz`。

---

## 2. 操作步骤清单

### A. Clerk 认证服务 (User & Auth)
Clerk 是我们身份认证的核心，必须将主域名切换过去。

1.  **添加域名**：
    *   登录 [Clerk Dashboard](https://dashboard.clerk.com/)。
    *   进入 **Configure** -> **Domains**。
    *   点击 **Add Domain**，输入 `izumilife.xyz`。
2.  **DNS 验证** (必须完成)：
    *   Clerk 会提供约 3-5 条 CNAME 记录。
    *   前往 **域名注册商后台** (如阿里云/腾讯云) 的 DNS 解析设置。
    *   逐条添加这些 CNAME 记录。
    *   等待 Clerk 验证通过 (变绿)。
3.  **设为主域名 (Primary)**：
    *   验证通过后，点击域名右侧可能有的 `...` 菜单，选择 **Set as Primary**。
    *   **注意**：这一步会改变 Production Key。
4.  **更新 Key**：
    *   进入 **API Keys**。
    *   复制新的 **Publishable Key** (`pk_live_...`)。
    *   更新项目代码 `web/config.js`。

### B. Vercel 部署服务 (Frontend Hosting)
为了让用户能通过 `https://izumilife.xyz` 访问网站，必须在 Vercel 进行绑定。

1.  **添加域名**：
    *   登录 [Vercel Dashboard](https://vercel.com/dashboard)。
    *   进入项目 **Settings** -> **Domains**。
    *   输入 `izumilife.xyz` 并添加。
    *   建议同时添加 `www.izumilife.xyz` 并设置重定向到根域名 (或者反过来)。
2.  **DNS 解析**：
    *   Vercel 会提示 DNS 配置错误。
    *   **A 记录**：主机记录 `@`，记录值填 Vercel 提供的 IP (通常是 `76.76.21.21`)。
    *   **CNAME 记录**：主机记录 `www`，记录值 `cname.vercel-dns.com`。
    *   *去域名商后台添加上述记录*。
3.  **等待生效**：
    *   Vercel 会自动申请 SSL 证书，通常几分钟内可用。

### C. 后端服务 (Backend API)
如果后端域名也发生了变更，或者需要配置跨域许可 (CORS)。

1.  **更新 CORS 白名单** (`apps/app.py`)：
    *   确保 `allow_origins` 列表中包含了新域名：
        ```python
        "https://izumilife.xyz",
        "https://www.izumilife.xyz",
        ```
2.  **验证后端可用性**：
    *   检查前端 `web/config.js` 中的 `API_BASE_URL`。
    *   目前指向：`https://izumiai.site:7701/api`。
    *   **风险提示**：如果 backend 域名 (`izumiai.site`) 也属于被封禁范围或同源失效，需及时更换为服务器 IP 或新域名 (如 `api.izumilife.xyz`)。

### D. Google OAuth Social Login 配置
如果用户使用 Google 账号登录时提示 `Error 400: redirect_uri_mismatch`，必须更新 Google OAuth 客户端设置。

1.  **登录 GCP 控制台**：
    *   访问 [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)。
    *   找到 OAuth 2.0 Web Client ID 并点击编辑。
2.  **更新授权来源 (Authorized JavaScript origins)**：
    *   添加新域名：`https://izumilife.xyz`
    *   添加新域名：`https://www.izumilife.xyz`
3.  **更新重定向 URI (Authorized redirect URIs)**：
    *   **必须匹配 Clerk 的回调地址**。
    *   可在 Clerk Dashboard -> **User & Authentication** -> **Social Connections** -> Google (⚙️) 中查看。
    *   通常格式为：`https://clerk.izumilife.xyz/v1/oauth_callback`
4.  **保存**：
    *   等待 1-5 分钟生效。

### E. 后端 JWT 验证配置 (关键)
后端服务需要验证前端传来的 Token。由于域名变更，Clerk 的签发者 (Issuer) 和允许的接收方 (Authorized Parties) 都变了。
**必须登录您的后端服务器，更新环境变量 (`.env` 或 Docker 环境变量):**

1.  **CLERK_JWKS_URL** (公钥地址):
    *   前往 Clerk Dashboard -> **API Keys** -> 点击右下角 **Advanced** -> 复制 **JWKS URL**。
    *   通常格式：`https://clerk.izumilife.xyz/.well-known/jwks.json` (如果配置了 CNAME) 或 Clerk 提供的默认 URL。
    *   **服务器配置修改**：
        ```bash
        CLERK_JWKS_URL=https://<your-new-jwks-url>
        ```
2.  **CLERK_AUTHORIZED_PARTIES** (白名单):
    *   必须包含新的前端域名，否则登录会报 403 Forbidden。
    *   **服务器配置修改**：
        ```bash
        CLERK_AUTHORIZED_PARTIES=https://izumilife.xyz,https://www.izumilife.xyz,https://project-feishu-bot.vercel.app
        ```
3.  **重启后端服务**：
    *   修改配置后，务必重启后端程序以生效。

---

## 3. 合规与申诉 (Google Safe Browsing)
为了防止新域名再次被封，必须保持合规页面的可访问性。

*   **隐私政策**：`web/privacy.html` (已创建)
*   **服务条款**：`web/terms.html` (已创建)
*   **联系方式**：确保页面底部包含真实有效的联系方式 (GitHub/Twitter/WeChat)。
*   **登录页**：登录卡片底部已添加上述条款链接。

---

## 4. 常见问题 (Troubleshooting)

*   **登录后跳转回 Vercel 域名？**
    *   如果只在 Clerk 配置了域名，没在 Vercel 配置，Clerk 可能会跳转回 `vercel.app`。
    *   **解决方法**：完成上述 "B. Vercel 部署服务" 步骤，并让用户统一通过 `izumilife.xyz` 访问。
*   **Clerk 报错 "Invalid Origin"**
    *   检查 `web/config.js` Key 是否为最新的 `pk_live`。
    *   确保访问的域名与 Clerk 后台绑定的 Primary Domain 一致。

---
*最后更新时间：2026-01-30*
