# 飞书机器人与前端重构计划 (New Frame)
## 1. 核心目标
将现有的后端 `analyze` 和 `save` 能力与飞书前端深度整合，实现“即时响应、可视化编辑、闭环操作”的高效交互体验。同时规划独立 Web App 前端以应对未来更复杂的交互需求。
## 2. 飞书卡片交互重构设计
### 2.1 触发机制 (Trigger)
采用 POST 模式，基于 **Title (标题)** 进行精准路由分发：
*   **Diet (饮食)**: 匹配 `Diet`, `diet`, `d`, `D`
*   **Keep (运动/健康)**: 匹配 `Keep`, `keep`, `k`, `K`
### 2.2 交互流程 (Workflow)
#### A. 初始阶段：即时反馈 (Immediate Response)
*   **动作**: 用户发送带图片/文本的 POST 请求。
*   **系统**: 不等待分析结果，**立即**返回一张“编辑/加载卡片”。
*   **卡片内容**:
    *   **用户备注 (User Note)**: 输入框，回显用户发送的文本，允许立即修改。
    *   **时间/日期**: 日期选择器 + 时间段下拉菜单 (早餐/午餐/晚餐/加餐)，默认当前时间。
    *   **状态栏**: 显示“正在识别中...”动画或图标。
    *   **后台**: 启动异步分析任务 (Diet/Keep Analyze)。
#### B. 分析完成：数据展示 (Data Presentation)
*   **动作**: 后端分析完成，异步更新同一张卡片。
*   **Diet 卡片更新**:
    *   **识别结果**: 展示识别到的菜品列表 (可编辑名称/热量预估)。
    *   **营养概览**: 动态展示卡路里、三大营养素 (如有)。
*   **Keep 卡片更新**:
    *   **趋势数据**: (暂无 Keep 复杂分析) 展示暂时的“简易建议”，包含过去几日的数据对比和变化趋势。
    *   **数据录入**: 允许手动校正运动数据 (如时长、消耗)。
#### C. 功能操作区 (Action Bar)
位于卡片底部，提供核心操作：
1.  **重新识别 (Re-Analyze)** (Refresh Icon)
    *   **逻辑**: 用户修改 `User Note` 后点击。
    *   **行为**: 携带最新的 Note 和图片 ID 再次调用 Backend Analyze API。
    *   **缓存**: 需在 Redis/内存中缓存 `image_key`，有效期建议 1 小时 (超过 3 张或超时则失效，卡片显示“已失效”)。
    *   **UI**: 状态重置为“正在识别...”。
2.  **更新建议 (Update Advice)** (Magic Icon)
    *   **逻辑**: 基于当前卡片上的数据生成/刷新建议。
    *   **状态**: 初始为灰色 (或显示上次建议)。只有当数据发生显著变化 (如用户手动修改了菜品) 或用户强制点击时激活。
    *   **缓存**: 建议内容需缓存。如果数据未变，直接读取缓存，避免浪费 LLM Token。
3.  **保存数据 (Save Data)** (Check/Save Icon)
    *   **逻辑**: 提交卡片上的最终数据 (Final State) 到后端。
    *   **接口**: 调用通用 `Update/Append` 接口 (即 `DietCommitRequest`)，将数据写入 `user_data`。
    *   **反馈**: 保存成功后，按钮变绿或卡片转为“已归档”只读状态。
### 2.3 关键组件与技术细节
*   **下拉菜单**:
    *   `diet_time`: 早/午/晚/加餐 (基于时间自动预选)。
    *   `date`: 日期选择器 (默认为 `today`)。
*   **状态缓存策略**:
    *   利用 `message_id` 作为 Key。
    *   缓存内容: `original_image_keys`, `current_analysis_result`, `last_advice_hash`, `user_note_draft`.
    *   淘汰策略: LRU (最近最少使用)，保留最近 5-10 条会话上下文即可。
    *   **实现建议**: 在 Redis 中存储 `card_id` -> `{user_note, image_keys, current_result}` 的临时映射，TTL 1小时。

### 2.4 涉及文件与改动 (Technical Implementation Map)
*   **`message_handler.py`**:
    *   新增 `_handle_keep_analyze_async`: 发送占位符 -> 调用后端 -> 渲染 `KeepAnalysisCard`。
    *   重构 `_handle_diet_analyze_async`: 适配新的“输入优先”交互逻辑。
*   **卡片构建器 (New Files)**:
    *   `Module/Adapters/feishu/cards/keep_cards/keep_analysis_card.py`: 实现 `KeepAnalysisCardBuilder`。
    *   `Module/Adapters/feishu/cards/diet_cards/diet_analysis_card.py`: 升级为交互式卡片，增加 `Diet Time` Select 组件。
*   **`card_handler.py`**:
    *   注册动作: `keep_re_analyze`, `keep_save`, `diet_re_analyze`, `diet_save`.
    *   逻辑: 从 Cache 读取原始 Context，合并当前 Form 数据进行二次提交。
---
## 3. Web App 独立前端深度规划 (Strategic Roadmap)

既然确定要独立 App 化，我们需要直接采用“生产级”架构，而非临时的过渡方案。

### 3.1 核心布局：Chat + Dynamic Side Panel (Copilot 模式)
不再是简单的“聊天窗口”，而是采用**三栏式布局** (桌面端) / **抽屉式布局** (移动端)：

*   **左侧 (导航/历史)**: 快速切换 Session，查看历史记录。
*   **中间 (Chat Flow)**:
    *   传统的对话流，用于发送指令（“分析这个图片”、“昨天的热量是多少”）。
    *   **关键点**: 对话气泡中不再包含复杂的编辑表格，而是只显示“摘要”或“卡片入口”。
*   **右侧 (Dynamic Artifact Panel / 动态交互面板)**:
    *   这是 React/HTML 的核心优势区域。当用户点击“分析”或聊天中出现需要确认的数据时，右侧面板展开。
    *   **常驻状态**: 这里像一个“草稿纸”或“控制台”。
    *   **Keep/Diet 场景**: 右侧显示上传的图片（支持**拖拽、裁剪、放大**），下方是结构化的数据表单 (Form)。

### 3.2 交互优势：HTML App vs. 飞书卡片

| 特性 | 飞书卡片 (Server-Driven) | HTML Web App (Client-First) | 优势场景 |
| :--- | :--- | :--- | :--- |
| **状态更新** | **高延迟**: 点击 -> 后端处理 -> 发送新卡片json -> 渲染 (约1-2秒) | **零延迟**: 修改 State -> React 自动重渲染 (毫秒级)。仅在“保存”时请求后端。 | 滑动条调整体重、营养素微调 |
| **输入控件** | 仅限输入框、选择器、日期。不支持滑动条 (Slider) | **全能力**: Slider (滑动条), Switch, Drag & Drop (拖拽上传/排序), Canvas (图片标注)。 | 调整饮食占比、体重微调 |
| **图片交互** | 只能查看，不可编辑。 | **可编辑**: 支持图片裁剪、旋转、画笔标注 (比如圈出食物)。 | 修正识别区域 |
| **移动端** | 只能垂直堆叠，空间利用率低。 | **响应式**: **Bottom Sheet (底部抽屉)**。点击聊天卡片，底部弹出详细编辑页（占屏 80%），下滑关闭。 | 手机单手操作 |

### 3.3 技术栈与鉴权 (Authentication)
*   **框架**: **Next.js 14+ (App Router)** + **Tailwind CSS** + **ShadcnUI** (符合 Premium Design 要求)。
*   **状态管理**: **TanStack Query** (React Query) 用于前后端状态同步。
*   **鉴权方案 (强烈推荐)**: **Clerk**
    *   *理由*: 早期通过“通行证ID”虽然简单，但后期迁移成本极高。Clerk 开箱即用支持 Google/Apple 登录，且免费额度足以覆盖早期阶段。
    *   **集成方式**:
        1.  前端使用 `<ClerkProvider>`.
        2.  API 请求头携带 `Authorization: Bearer <token>`.
        3.  FastAPI 后端编写 Dependency 解析 JWT token 并映射到 `user_id`.

### 3.4 支付与商业化 (Payment & MoR)
*   **阶段一：验证期 (Seed)**
    *   **策略**: 手动转账 (微信/支付宝) -> Admin 面板手动开通权限。
    *   *优势*: 零手续费，直接接触核心用户，验证需求。
*   **阶段二：规模化 (Scale)**
    *   **策略**: 使用 **Merchant of Record (MoR)** 平台，如 **LemonSqueezy**.
    *   *优势*: 平台作为“经销商”处理全球税务 (Tax compliant)，你只需接收结算款。相比 Stripe 纯网关模式，MoR 更适合独立开发者（无需在早期注册复杂的海外公司实体）。
*   **模板参考**:
    *   **ShipFast**: 包含 Next.js + Tailwind + Stripe/LemonSqueezy 的成熟脚手架。
    *   **Makerkit**: 功能更全的 SaaS Starter。

### 3.5 Web App 实施指南 (纯 HTML + Clerk)
**方案调整**: 放弃 Next.js，采用**纯 HTML + JavaScript**。无需安装 Node.js/npm，直接写静态页面。

#### 技术栈
*   **前端**: 纯 HTML + Vanilla JS + CSS (可选 Tailwind CDN)
*   **鉴权**: Clerk JavaScript SDK (`@clerk/clerk-js`)，通过 `<script>` 标签引入
*   **部署**: **GitHub Pages** (免费、无需服务器资源)
*   **后端**: 现有的 Python FastAPI (已部署在远程服务器)

#### 目录结构
```
Project_Feishu_Bot/
├── web/                      # 新增：纯静态前端
│   ├── index.html            # 入口页 (登录/首页)
│   ├── dashboard.html        # 主界面 (Chat + Side Panel)
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   ├── auth.js           # Clerk 初始化与登录逻辑
│   │   ├── api.js            # 与 FastAPI 后端通信
│   │   └── app.js            # 主业务逻辑
│   └── config.js             # 配置 (API URL, Clerk Key)
└── ...
```

#### 关键步骤

1.  **Clerk 初始化 (纯 JS)**:
    在 HTML 的 `<head>` 中引入 Clerk SDK：
    ```html
    <script
      async
      crossorigin="anonymous"
      data-clerk-publishable-key="pk_test_YWR2YW5jZWQtcHVtYS01Mi5jbGVyay5hY2NvdW50cy5dZXYk"
      src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js"
      type="text/javascript"
    ></script>
    ```

2.  **登录/登出按钮**:
    Clerk 会自动渲染到指定的 `<div>`:
    ```html
    <div id="clerk-user-button"></div>
    <script>
      window.Clerk.load().then(() => {
        const userButtonDiv = document.getElementById("clerk-user-button");
        window.Clerk.mountUserButton(userButtonDiv);
      });
    </script>
    ```

3.  **获取 Token 调用后端 API**:
    ```javascript
    async function callBackendAPI(endpoint, data) {
      const token = await window.Clerk.session.getToken();
      const response = await fetch(`https://your-api.com${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      });
      return response.json();
    }
    ```

#### 部署方案：GitHub Pages
*   **优势**: 免费托管静态站点；不占用你的远程服务器资源 (40G 内存保持给 Python 后端)。
*   **步骤**:
    1.  在 GitHub 仓库 Settings -> Pages -> Source 选择 `main` 分支 `/web` 目录。
    2.  访问 `https://yourusername.github.io/Project_Feishu_Bot/` 即可。
*   **CORS 注意**: FastAPI 后端需要配置 `CORSMiddleware` 允许来自 GitHub Pages 域名的请求。

### 3.6 用户数据关联策略 (Feishu <-> Web)
如何让网页端登录的用户 (Clerk ID) 看到飞书端 (Feishu Open ID) 产生的数据？

**方案 A：手动映射 (MVP 推荐)**
*   **原理**: 早期用户极少（只有你自己或亲友）。
*   **操作**:
    1.  用户在网页端注册/登录 (生成 `clerk_user_id`, 如 `user_2p...`)。
    2.  管理员 (你) 在配置文件或环境变量中建立映射：
        ```json
        {
          "user_2pM...": "me"
        }
        ```
    3.  **后端改造**: 修改 `require_user` 依赖。当收到 Clerk Token 时，解析出 `clerk_id`，查映射表转换为对应的 `user_id`，然后用这个 ID 去查数据。
*   **优点**: 开发成本几乎为零，数据完全隔离，无需复杂的"账号绑定"界面。

**方案 B：统一账户表 (长期)**
*   **原理**: 数据库新建 `User` 表，包含 `id (uuid)`, `clerk_id`, `feishu_id` 字段。
*   **操作**: 业务逻辑全部基于内部 `uuid`。登录时动态查找对应的 `uuid`。

建议现阶段采用 **方案 A**。

### 3.7 实施建议
在项目根目录创建 `web/` 文件夹，编写纯 HTML 页面。通过 GitHub Pages 发布，前端零资源消耗。

---
## 4. 下一步行动 (Next Steps)
1.  **Web App (当前优先)**:
    *   创建 `web/` 目录结构和基础 HTML 页面。
    *   集成 Clerk 登录。
    *   实现 File Upload -> API Call -> Render Result 链路。
    *   配置 GitHub Pages 部署。
2.  **Feishu Integrations**:
    *   更新 `message_router` 支持 Title 正则路由。
    *   新建 `keep_analysis_card.py` 和 `diet_analysis_card.py` (Interactive Version)。
    *   在 `message_handler` 中实现 `handle_keep_analyze_async`。
3.  **Backend Support**:
    *   添加 CORS 配置允许 GitHub Pages 域名。
    *   准备 Clerk JWT 验证的 FastAPI Dependency。