# 飞书机器人与前端重构计划 (New Frame)
## 1. 核心目标
将现有的后端 `analyze` 和 `save` 能力与飞书前端深度整合，实现“即时响应、可视化编辑、闭环操作”的高效交互体验。同时规划独立 Web App 前端以应对未来更复杂的交互需求。

## 1.1 产品交互原则（必须长期遵守）
- **避免破坏与不可逆操作**：除非收益非常明确，否则优先使用“启用/停用（勾选）”“撤销/恢复”这类可逆交互，避免直接删除等破坏性操作。AI 自动识别的数据尤其如此，默认应可回退。
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

---
## 3.8 当前进度（截至 2026-01-11）
### 已完成
- **Web 基础框架**：`web/` 纯静态前端 + Clerk 登录 + 与 FastAPI API 通信
- **三栏布局雏形**：左侧历史/入口 + 中间确认面板 + 右侧对话输入；移动端确认面板抽屉化
- **Diet**
  - **菜式表格编辑**：支持编辑蛋白/脂肪/碳水/膳食纤维/钠/重量
  - **启用/停用交互**：AI 识别菜式禁止删除，改为勾选启用与否；仅用户新增菜式允许删除
  - **动态汇总**：总能量/三大营养/纤维/钠/总重量自动加总
- **Keep**
  - 识别结果保持只读展示（不提供编辑入口）
- **Profile（前端先行）**
  - 增加 Profile 子界面：时区 + Diet/Keep 目标配置
  - 增加“能量显示单位”切换（默认 kJ，立即生效）

### 已知问题（后续处理）
- **移动端整体适配仍需细化**：目前优先保证“输入栏置底 + 确认面板可呼出/折叠 + 无横向滚动编辑”的可用性，其他视觉与交互细节待集中优化。

### 3.9 Web 前端 TODO List

> 优先级说明：S=阻塞级（影响核心功能）、A=高优（影响用户体验）、B=中优（体验优化）、C=低优（锦上添花）

#### 待修复瑕疵

| 优先级 | 编号 | 问题描述 | 涉及范围 | 状态 |
|--------|------|----------|----------|------|
| **S** | BUG-001 | 点击"重新分析"后保存的数据变空 `{}` | 前端 `collectEditedData` 或状态管理 | 🔴 搁置（未复现，搁置） |
| **S** | BUG-002 | DIET/KEEP：保存未正确沿用 analyze 返回的 `occurred_at`（应缓存并最终写入对应数据与文件） | 前端 `saveRecord` + 后端 storage | ✅ 已修 (2026-01-15) |
| **B** | BUG-003 | advice 文本未渲染 markdown 格式（换行、粗体等） | 前端 `renderAdvice` | ✅ 已修 (2026-01-13) |
| **S** | BUG-004 | KEEP：多图场景保存会把多次分析/多张图的结果混在一起（数据串联/污染） | 前端 Session/Version + 保存链路 | ✅ 已修 (2026-01-15) |
| **A** | BUG-005 | DIET：编辑营养素后自动重算触发重新渲染，输入框焦点丢失，导致无法连续输入（例如 2.1 改 12） | 前端 `updateDish/updateIngredient` → `recalculateDietSummary` → `renderDietDishes` | ✅ 已修 (2026-01-15) |

#### 待开发功能

| 优先级 | 编号 | 功能描述 | 涉及范围 | 状态 |
|--------|------|----------|----------|------|
| **A** | FEAT-001 | 营养摄入可视化图表（详见 §3.10） | 前端 ECharts + 交互 | ✅ 已完成 (2026-01-14) |
| **A** | FEAT-003 | 失败一键重试机制（避免重新输入） | 前端 Error UX | ✅ 已完成 (2026-01-15) |
| **A** | FEAT-004 | 营养点评区域可折叠（详见 §3.10） | 前端 UI | ✅ 已完成 (2026-01-14) |
| **B** | FEAT-002 | 营养标签产品名下拉选择（从 product library 选择） | 前端 UI + API | ⬜ 待开发 |
| **B** | OPT-001 | 优化响应超时(60s)与请求耗时日志 | 后端 Server | ✅ 已完成 (2026-01-15) |
| **B** | REFACTOR-001 | dashboard.js 拆分重构（2290行→模块化） | 前端架构 | ✅ 已完成 (2026-01-14) |
| **B** | REFACTOR-002 | get_product_memories 逻辑与数据结构重构 | 后端 Logic | ⬜ 待规划 |

#### 已完成 (2026-01-13)

| 编号 | 问题/功能 | 解决方案 |
|------|----------|----------|
| P0 | 等比缩放开关 | 每个成分独立开关，用 ⚖ 图标表示 |
| P2 | advice 自动触发 | 分析完成后自动请求建议，添加 loading 状态 |
| P1 | labels_snapshot 展示 | 底部可折叠区域，支持编辑 product_name/brand/variant/custom_note |
| FIX | advice 响应解析错误 | 修复 `response.result.advice_text` 解包 |
| FIX | 等比缩放图标不直观 | 从 🔗/⛓️ 改为 ⚖（由用户手动调整） |

#### 已完成 (2026-01-14)

| 编号 | 问题/功能 | 解决方案 |
|------|----------|----------|
| REFACTOR-001 | dashboard.js 拆分重构 | 2342行 → 910行，拆分为 9 个模块 |
| FIX | 分析失败后一直转圈 | `showError()` 中添加 `updateStatus('')` 清除加载状态 |
| FIX | 总能量单位显示错误 | 内部统一 kcal 计算，展示按 Profile 能量单位(kJ/kcal)换算；保存避免二次换算 |
| FIX | 营养进度图表可读性 | 6条标签全显示、单行标签、进度条更粗、X轴对 >100% 动态扩展、配色优化 |
| FIX | 图表 Tooltip 提示增强 | 目标后追加百分比；脂肪/钠用“还剩余/已超出”，其余用“已摄入” |
| FIX | 折叠交互统一 | 营养进度与点评右上角折叠按钮；点评默认展开、仅手动点击收起 |

#### 已完成 (2026-01-15)

| 编号 | 问题/功能 | 解决方案 |
|------|----------|----------|
| BUG-005 | 连续输入焦点丢失 | `diet-edit.js` 引入 `updateDishDOM/updateDishRowDOM` 实现 targeted DOM update，避免全量重绘 |
| UI | Profile 按钮样式不统一 | 将 Profile 界面操作按钮统一为 `.btn .btn-primary` 风格，移除旧的 `.profile-btn` |
| UI | Save Profile图标对齐 | 移除图标渲染的 `sm` 参数，与 Save Record 保持尺寸一致 |
| UX | 失败一键重试 | 分析失败页面增加"重试"按钮，保留上下文重新发起请求 |
| OPT | API超时优化 | API请求默认超时改为120s，增加耗时日志，防止LLM分析超时 |
| BUG-002 | Diet/Keep保存日期错误 | 修复前端 `saveDiet` 参数透传漏洞；后端 Advice 支持按事件日期获取上下文；Keep 保存自动提取事件时间 |
| BUG-004 | Keep数据保存异常 | 前端强制启用 `unified` 模式，后端完整实现多事件拆包保存逻辑，修复数据污染问题 |

**重构后模块清单**：
| 模块 | 行数 | 职责 |
|------|------|------|
| `dashboard.js` | ~290 | 主控制器：初始化、状态管理、路由 |
| `utils/energy.js` | ~55 | 能量转换（kcal/kJ、宏量计算） |
| `utils/image.js` | ~80 | 图片处理（上传、预览、哈希） |
| `utils/text.js` | ~35 | 文本处理（Markdown 渲染） |
| `modules/parser.js` | ~145 | 后端数据解析与转换 |
| `modules/session.js` | ~135 | Session/消息卡片渲染与管理 |
| `modules/analysis.js` | ~150 | 分析流程（API调用、版本管理） |
| `modules/diet-render.js` | ~420 | Diet 渲染（结果、表格、移动端） |
| `modules/diet-edit.js` | ~290 | Diet 编辑（增删改、汇总） |
| `modules/keep-render.js` | ~105 | Keep 渲染（体重、睡眠、围度） |
| `modules/profile.js` | ~82 | Profile 工具函数 |
| `modules/storage.js` | ~140 | 存储操作（保存、历史） |

> **注**：`renderProfileView` (~250行 HTML 模板) 仍在 dashboard.js 中，待后续用 `<template>` 标签优化。

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

## 5. 补充参考 (Implementation Details)

### 2.5 缓存策略补充 (Smart Caching)
*来源：diet_bot_specs_v2.md*

为了节省 Token 并实现秒级响应，建议区分 **上下文缓存** 与 **结果缓存**：

1.  **Input Hash 计算**:
    *   针对建议生成，Input 是 `Food List + Weights`.
    *   `hash_key = md5(f"{date}|{meal_type}|sorted([{food_name}:{weight},...])")`
2.  **Advice Cache**:
    *   存储: `Redis Key: advice:{hash_key} -> "建议文本..."`
    *   **回退优化 (Revert Scenario)**: 用户如果把 "40g" 改成 "50g" (触发新生成)，又改回 "40g"，计算出的 hash_key 相同，应直接命中缓存，无需再次调用 LLM。
3.  **生命周期**:
    *   建议缓存有效期可设为 24小时 (跨卡片复用)。
    *   卡片上下文 (`message_id` 绑定) 随卡片生命周期结束（如 1 小时后或归档后）清理。

---

## 6. 周分析功能 (Weekly Analysis) - Diet & Keep

### 6.1 功能概述
为 Diet 和 Keep 模块提供周维度的综合分析能力，包括：
- 餐食质量分析与评分
- 下周餐食建议
- 热量校准系数估算
- 目标进度对比
- 围度变化分析
- 可视化趋势图表

### 6.2 目录结构
保持与 `diet`/`keep` 一致的扁平结构：
```
apps/weekly_analysis/
├── __init__.py
├── api.py                  # FastAPI 端点
├── data_collector.py       # 周数据采集
├── analysis_schema.py      # Pydantic Schema (AI输出结构)
├── weekly_prompt.py        # AI 分析 Prompt
├── calorie_math.py         # 热量校准数学计算（非AI）
├── chart_config.py         # ECharts 配置生成
└── usecases/
    └── weekly_analysis_usecase.py  # 核心业务逻辑
```

### 6.3 MVP 拆分与进度

#### MVP1：数据采集 + 基础API骨架 ✅ 代码完成，待验证
- [x] 创建 `apps/weekly_analysis/` 目录
- [x] `data_collector.py`: 采集指定周的 diet/keep 数据
  - `WeeklyDataBundle` 数据类含计算属性判断分析触发条件
  - 复用 `RecordService` 的已有方法
- [x] `api.py`: 基础端点 `/api/weekly-analysis/data`
  - 支持 `week_offset` 参数（-1=上周, 0=本周）
  - 支持直接指定 `week_start` 日期
- [x] 注册到 `apps/app.py`
- [ ] 验证数据采集正确性（需启动后端服务测试）

#### MVP2：AI综合分析 ✅ 代码完成
- [x] `analysis_schema.py`: 定义 AI 输出的 Pydantic Schema
  - `WeeklyAnalysisResult` 主模型，包含可选的子分析模块
  - `WeeklyDietAnalysis`, `MealSuggestion`, `CalorieCalibration`, `GoalProgress`, `DimensionChange`
- [x] `weekly_prompt.py`: 构建综合分析 Prompt
  - 动态格式化数据、根据可用性生成条件指令
- [x] `usecases/weekly_analysis_usecase.py`: 调用 AI 生成分析
  - 支持结构化JSON (`execute_async`) 和纯文本 (`execute_text_async`) 两种输出
- [x] API 端点 `/api/weekly-analysis/report` 完善
  - 支持 `output_mode=json|text`
  - 集成并发控制和限流

#### MVP3：热量校准 + 图表
- [ ] `calorie_math.py`: 差值法热量校准计算
- [ ] `chart_config.py`: 生成 ECharts 配置 JSON
- [ ] 在 report 中整合图表数据

#### MVP4：Web 前端集成
- [ ] 左侧菜单添加"📅 周报"入口
- [ ] 周报展示页面（含 ECharts 图表）
- [ ] 交互调整（周切换等）

#### MVP5：飞书集成
- [ ] 在现有周报流程 (`routine_daily_element.py`) 中追加饮食健康分析章节
- [ ] 飞书云文档内容生成

### 6.4 数据源与条件

| 数据 | 来源 | 采集逻辑 |
|-----|------|---------|
| Diet Records | `ledger_{date}.jsonl` | 周区间内所有文件 |
| Dish Library | `dish_library.jsonl` | 取最新100条 |
| Scale Records | `scale_{yyyy_mm}.jsonl` | 周区间内的记录 |
| Sleep Records | `sleep_{yyyy_mm}.jsonl` | 周区间内的记录 |
| Dimensions | `dimensions_{yyyy_mm}.jsonl` | 周内 + baseline(周前最后一条) |
| Profile | `profile.json` | 用户目标配置 |
| Preferences | `preferences.json` | 🆕 个性化饮食偏好 |

### 6.5 分析触发条件

| 分析项 | 触发条件 |
|-------|---------|
| 餐食质量分析 | `len(diet_records) > 0` |
| 下周餐食建议 | `len(diet_records) > 0 and len(dish_library) > 0` |
| 热量校准 | `len(diet_records) >= 3 and len(scale_records) >= 2` |
| 目标进度 | `profile is not None` |
| 围度分析 | 至少2个不同日期的围度数据 |

### 6.6 个性化偏好配置
新增 `user_data/<user_id>/diet/preferences.json`:
```json
{
  "fixed_meals": {
    "breakfast": "燕麦脱脂牛奶+水果（不建议替换）"
  },
  "dietary_restrictions": ["尽量少外食", "周末允许放松"],
  "notes": "优先保证蛋白质摄入"
}
```

---

## 3.10 营养摄入可视化与交互优化 (FEAT-001 + FEAT-004)

### 3.10.1 FEAT-001：营养摄入可视化图表

#### 核心目标
创建一个**可交互的多层柱状/条形图表**，清晰展示三层营养数据的对比关系：
1. **本次分析值** (This Meal)：当前正在编辑的菜式汇总，与 checkbox 状态**实时联动**
2. **今日已摄入** (Today's Intake)：今天已保存的所有饮食记录汇总（不含本次未保存的）
3. **每日目标值** (Daily Target)：来自 `profile.diet` 的目标配置（如果有）

#### 可视化方案：ECharts 堆叠柱状图

```
          能量      蛋白质      脂肪       碳水       纤维        钠
     ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
 100%│   ▓▓    │  ███    │   ██    │   ██    │    █    │  ████   │ ← 目标线
     │   ▓▓    │  ███    │ ░░██    │ ░░██    │  ░░█    │ ░░████  │
  50%│ ░░▓▓    │░░░███   │ ░░██    │ ░░██    │  ░░█    │ ░░████  │
     │ ░░▓▓    │░░░███   │ ░░██    │ ░░██    │  ░░█    │ ░░████  │
   0%└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘

     ▓▓ = 本次分析 (This Meal)    ░░ = 今日已摄入 (Today's Intake)
     ── = 目标线 (Daily Target)
```

#### 数据联动规则

| 交互行为 | 图表响应 |
|----------|----------|
| 勾选/取消勾选某个菜式 | 重新计算 `currentDietTotals`，实时更新"本次分析"柱 |
| 编辑菜式的营养数值 | 重新计算 `currentDietTotals`，实时更新"本次分析"柱 |
| 切换 Ingredient 比例模式 | 重新计算 Dish Totals，联动更新 |
| 保存记录成功 | "今日已摄入" 柱更新（需重新获取今日汇总） |

#### 图例交互

图表图例 (Legend) 支持**独立点击切换显示/隐藏**：
- 点击 `本次分析` → 隐藏/显示该系列的柱子
- 点击 `今日已摄入` → 隐藏/显示该系列的柱子
- 点击 `每日目标` → 隐藏/显示目标线（markLine）

#### 技术实现

**1. 新增 API：获取今日已摄入汇总**

```python
# apps/diet/api.py
@router.get("/diet/today-summary")
async def get_today_summary(user_id: str = Depends(require_user)):
    """获取今日已保存的饮食记录汇总"""
    records = record_service.get_diet_records_for_date(user_id, date.today())
    summary = {
        "total_energy_kcal": 0,
        "total_protein_g": 0,
        "total_fat_g": 0,
        "total_carb_g": 0,
        "total_fiber_g": 0,
        "total_sodium_mg": 0,
        "record_count": len(records)
    }
    for r in records:
        for dish in r.get("dishes", []):
            if dish.get("enabled", True):
                # 累加营养素（逻辑复用 RecordService）
                ...
    return summary
```

**2. 前端模块：`modules/nutrition-chart.js`**

```javascript
const NutritionChartModule = {
    chartInstance: null,
    todaySummary: null,  // 缓存今日已摄入

    async init(container) {
        // 获取今日已摄入
        this.todaySummary = await API.get('/diet/today-summary');
        this.render(container);
    },

    render(container) {
        if (typeof echarts === 'undefined') return;

        const chart = echarts.init(container);
        const option = this.buildOption();
        chart.setOption(option);
        this.chartInstance = chart;

        // 监听图例点击
        chart.on('legendselectchanged', (params) => {
            console.log('Legend changed:', params.selected);
        });
    },

    // 外部调用：当 checkbox 或数值变化时更新
    updateCurrentMeal(totals) {
        if (!this.chartInstance) return;
        this.chartInstance.setOption({
            series: [{ id: 'this-meal', data: this.toDataArray(totals) }]
        });
    },

    buildOption() {
        const targets = Dashboard.profile?.diet || {};
        const current = Dashboard.currentDietTotals || {};
        const today = this.todaySummary || {};

        // ... 完整 ECharts 配置
    }
};
```

**3. CSS 样式**

```css
.nutrition-chart-container {
    margin: var(--spacing-md) 0;
    padding: var(--spacing-md);
    background: var(--color-bg-tertiary);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    min-height: 200px;
}

.nutrition-chart-wrapper {
    width: 100%;
    height: 220px;
}

.nutrition-chart-legend {
    display: flex;
    justify-content: center;
    gap: 16px;
    margin-top: 10px;
    flex-wrap: wrap;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
}

.legend-item.disabled {
    opacity: 0.4;
    text-decoration: line-through;
}

.legend-color {
    width: 12px;
    height: 12px;
    border-radius: 2px;
}
```

**4. 颜色定义**

| 系列 | 颜色 | 说明 |
|------|------|------|
| 本次分析 | `#6366f1` (Indigo) | 品牌主色，表示当前操作 |
| 今日已摄入 | `#22c55e` (Green) | 已完成/已保存的意义 |
| 每日目标 | `rgba(255,255,255,0.3)` 虚线 | 作为参考线，不应抢占视觉 |

#### 布局位置

图表位于**营养汇总区域 (`.nutrition-summary`) 下方、AI 营养点评上方**：

```
┌──────────────────────────────────────┐
│  🍽️ 饮食记录  ·  3 种食物 · 午餐     │  ← Header
├──────────────────────────────────────┤
│  ┌────────────┐  ┌────┬────┬────┐    │
│  │ 188 kcal   │  │P 3g│F 4g│C 42│    │  ← 营养汇总 (只读)
│  │ 总能量     │  │纤维│钠  │重量│    │
│  └────────────┘  └────┴────┴────┘    │
├──────────────────────────────────────┤
│  📊 营养进度                          │  ← FEAT-001: 图表区域
│  ╔════════════════════════════════╗  │
│  ║   [柱状图]                      ║  │
│  ║   能量  蛋白  脂肪  碳水  ...    ║  │
│  ╠════════════════════════════════╣  │
│  ║ ● 本次  ● 今日  ─ ─ 目标        ║  │  ← 可交互图例
│  ╚════════════════════════════════╝  │
├──────────────────────────────────────┤
│  💡 AI 营养点评  [▼]                  │  ← FEAT-004: 可折叠
│  （点评内容...）                      │
├──────────────────────────────────────┤
│  食物明细                             │
│  ...                                  │
└──────────────────────────────────────┘
```

---

### 3.10.2 FEAT-004：营养点评区域可折叠

#### 需求背景
营养点评文字通常较长，占据较多垂直空间，在用户需要专注编辑下方"食物明细"数值时，会造成滚动距离增加。提供折叠功能可以让用户在需要时隐藏点评内容，方便操作。

#### 交互设计

| 状态 | 显示内容 | 触发方式 |
|------|----------|----------|
| **展开 (默认)** | 标题 + 折叠图标 `▼` + 完整点评内容 | 页面初始加载 |
| **折叠** | 仅标题 + 展开图标 `▶` | 点击标题区域 |

```
展开状态:
┌─────────────────────────────────────┐
│ 💡 AI 营养点评                   ▼  │  ← 点击任意位置可折叠
├─────────────────────────────────────┤
│ 你好！根据你的营养摄入情况，...      │
│ 1. 餐食总结...                       │
│ 2. 今日进展分析...                   │
│ 3. 后续建议...                       │
└─────────────────────────────────────┘

折叠状态:
┌─────────────────────────────────────┐
│ 💡 AI 营养点评                   ▶  │  ← 点击展开
└─────────────────────────────────────┘
```

#### HTML 结构变更

```html
<!-- Before (current) -->
<div id="advice-section" class="advice-section">
  <div class="advice-header">
    <div class="dishes-title">💡 AI 营养点评</div>
    <span id="advice-status" class="advice-status"></span>
  </div>
  <div id="advice-content" class="advice-content">...</div>
</div>

<!-- After (with collapse) -->
<div id="advice-section" class="advice-section">
  <div class="advice-header collapsible" onclick="Dashboard.toggleAdviceSection()">
    <div class="dishes-title">💡 AI 营养点评</div>
    <div class="advice-header-right">
      <span id="advice-status" class="advice-status"></span>
      <span class="advice-toggle-icon" id="advice-toggle-icon">▼</span>
    </div>
  </div>
  <div id="advice-content" class="advice-content">...</div>  <!-- 可添加 .collapsed -->
</div>
```

#### CSS 样式

```css
.advice-header.collapsible {
    cursor: pointer;
    user-select: none;
}

.advice-header.collapsible:hover {
    background: rgba(255, 255, 255, 0.03);
}

.advice-header-right {
    display: flex;
    align-items: center;
    gap: 8px;
}

.advice-toggle-icon {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    transition: transform 0.2s ease;
}

.advice-section.collapsed .advice-toggle-icon {
    transform: rotate(-90deg);
}

.advice-content {
    transition: max-height 0.3s ease, opacity 0.2s ease, padding 0.3s ease;
    overflow: hidden;
}

.advice-section.collapsed .advice-content {
    max-height: 0;
    opacity: 0;
    padding-top: 0;
    padding-bottom: 0;
}
```

#### JavaScript 方法

```javascript
// diet-render.js 或 dashboard.js
toggleAdviceSection() {
    const section = document.getElementById('advice-section');
    if (!section) return;

    section.classList.toggle('collapsed');

    // 保存折叠状态到 sessionStorage（同会话保持）
    const isCollapsed = section.classList.contains('collapsed');
    sessionStorage.setItem('dk_advice_collapsed', isCollapsed ? '1' : '0');
},

// 在 renderDietResult 中恢复状态
restoreAdviceState() {
    const collapsed = sessionStorage.getItem('dk_advice_collapsed') === '1';
    if (collapsed) {
        document.getElementById('advice-section')?.classList.add('collapsed');
    }
}
```

---

### 3.10.3 实施计划

| 阶段 | 任务 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 1 | 新增 `/diet/today-summary` API | `apps/diet/api.py`, `record_service.py` | 高 |
| 2 | 创建 `nutrition-chart.js` 模块 | `web/js/modules/nutrition-chart.js` | 高 |
| 3 | 修改 `diet-render.js` 渲染图表容器 | `web/js/modules/diet-render.js` | 高 |
| 4 | 添加图表 CSS 样式 | `web/css/dashboard.css` | 高 |
| 5 | 实现 checkbox/数值 → 图表联动 | `diet-edit.js`, `nutrition-chart.js` | 高 |
| 6 | 实现营养点评折叠 (FEAT-004) | `diet-render.js`, `dashboard.css` | 中 |
| 7 | 移动端适配（图表高度、触控） | `dashboard.css` | 中 |

---

### 3.10.4 移动端适配

- 图表高度适当缩减（180px → 150px）
- 图例改为横向滚动或换行
- 点击图例区域加大（便于触控）
- 营养点评默认折叠（移动端空间有限）

## 7. Keep 模块升级与数据治理方案 (Keep Upgrade)

针对现有 Keep 数据结构简单、新旧数据重叠、以及引入详细围度 (Body Metrics) 后的数据治理挑战，制定本升级方案。

### 7.1 核心挑战

1.  **数据重叠**：`scale` (体脂秤), `dimensions` (基础围度), `metrics` (20+详细围度) 存在字段交叉（如体重、腰围）。
2.  **Schema 割裂**：Keep 原有 Schema 字段命名 (`chest_cm`) 与新 Schema (`bust`) 不一致。
3.  **交互限制**：Keep 目前强制要求图片，不支持纯文本/混合输入。

### 7.2 数据治理策略 (Data Governance)

采用 **"Unified Schema, Distributed Storage" (统一模式，分步存储)** 策略：

#### A. 事件类型定义 (Event Types)

保持 Keep 事件类型的语义清晰，各司其职：

| 事件类型 | 职责 | 核心字段示例 | 数据来源 |
| :--- | :--- | :--- | :--- |
| `scale` | **成分分析** | `weight_kg`, `body_fat_pct`, `muscle_kg`, `moist_pct` | 智能体脂秤截图 |
| `dimensions` | **形体测量** | `bust`, `waist`, `hip_circ`, `thigh`, `calf`... | 皮尺测量 (文本/OCR) |
| `sleep` | **睡眠监测** | `duration_min`, `score`, `deep_sleep_min` | 手环/Keep截图 |

> **关键决策**：新引入的详细数据 (20+项) **不再创建新事件类型**，而是直接扩充 `dimensions` 事件的 Schema。未来的 `dimensions` 事件就是一个包含任意围度字段的字典。

#### B. Schema 统一映射 (Normalization)

在“解析层” (Parse Usecase) 做标准化，存入数据库时必须符合 `METRICS_SCHEMA` 定义的 Key。

| Keep 原字段 (旧) | 标准字段 (新 METRICS_SCHEMA) | 备注 |
| :--- | :--- | :--- |
| `chest_cm` | `bust` | 胸围 |
| `waist_cm` | `waist` | 腰围 |
| `hips_cm` | `hip_circ` | 臀围 (注意区分 metrics 里的 `hip_width`) |
| `thigh_cm` | `thigh` | 大腿围 |
| `arm_cm` | `arm` | 上臂围 |
| `weight_g` (Scale) | `weight` | 仅在聚合计算时关联，Scale 事件保留原字段名 |

#### C. 冲突解决与聚合计算 (Aggregation Logic)

当 `Calculator` 需要计算 WHR (腰臀比) 或 BMI 时，按以下优先级抓取数据：

1.  **Weight (体重)**:
    *   Priority 1: 同一天的 `scale` 事件 (机器测量最准)。
    *   Priority 2: 同一天的 `dimensions` 事件 (如果用户手填了体重)。
    *   Priority 3: 用户 `Profile` 中的 `latest_weight`。
2.  **Height (身高)**:
    *   Priority 1: 用户 `Profile` (成人身高基本不变)。
    *   Priority 2: `dimensions` 记录。
3.  **Waist/Hip (腰臀)**:
    *   Priority 1: `dimensions` 事件。

### 7.3 开发实施方案 (Implementation Plan)

#### Step 1: 后端统一解析 (True Unified Parser)

不拆分接口，而是将 `METRICS_SCHEMA` 的能力完整注入到现有的 `KeepUnifiedParseUsecase` 中。

1.  **改造 `apps/keep/usecases/parse_unified.py`**:
    *   **Current**: 仅识别 Scale, Sleep, Dimensions(基础)。
    *   **New**:
        *   Prompt 包含完整 `METRICS_SCHEMA`。
        *   指令：*"请识别输入中的所有健康数据，将其归类为 Scale(体脂), Sleep(睡眠), 或 Metrics(围度)。metrics 字段请严格遵循 Schema。"*
        *   兼容混合输入：例如一张体脂秤照片 + 一段 "腰围70" 的文本，需同时返回 `scale_event` 和 `metrics_event` (包含 waist: 70)。

2.  **API 调整**:
    *   更新 `/api/keep/analyze`，允许 `images` 为空列表 (支持纯文本输入)。

#### Step 2: 前端统一编辑器 (Unified Editor)

不再区分只读卡片，所有 Keep 解析结果均进入**“综合编辑页”**。

1.  **动态分区渲染**:
    *   根据 API 返回的 JSON 结构，动态展示存在的模块：
        *   **[模块 A] 身体成分 (Scale)**: 体重、体脂率、BMI...
        *   **[模块 B] 睡眠监测 (Sleep)**: 时长、深睡...
        *   **[模块 C] 身体围度 (Metrics)**: 
            *   *默认展示*: 胸/腰/臀/大腿/小腿基础字段。
            *   *权限控制*: 根据 `ENABLE_DETAILED_METRICS` 权限，决定是否渲染“添加更多字段”按钮及显示 Underbust/Arm/LTorso 等高级字段。
            *   *逻辑*: 即使无权限用户误传了 "LTorso: 30"，前端可选择隐藏或以只读方式展示，但不允许添加新高级字段。

2.  **交互优化**:
    *   支持一次性修改多类数据。
    *   保存时，前端将数据拆分为多个 Event (scale/sleep/dimensions) 提交，或提交给 Unified Save 接口由后端拆分。

### 7.4 示例 Unified Prompt (Chinese)

```text
你是一位全能的健康数据助手。请分析用户的输入（文本/图片），提取并归类所有健康数据。

**分类标准**:
1. **Scale (体脂/成分)**: 包含体重(weight)、体脂率(body_fat)、肌肉量等。
2. **Sleep (睡眠)**: 包含睡眠时长(duration)、评分、深睡/浅睡等。
3. **Metrics (身体围度)**: 包含以下标准字段：
   - bust(胸围), underbust(下胸围), waist(腰围), hip_circ(臀围)
   - arm(上臂), forearm(前臂), thigh(大腿), calf(小腿)
   - shoulder_circ(肩围), etc. (参考 METRICS_SCHEMA)

**输入**:
{user_note}

**输出 JSON 结构**:
{
  "scale_event": { "weight_kg": ..., "body_fat_pct": ... } | null,
  "sleep_event": { ... } | null,
  "metrics_event": { "bust": ..., "waist": ..., "metrics": { ... } } | null,
  "occurred_at": "YYYY-MM-DD HH:MM"
}
```

### 7.5 下一步动作
1. 确认上述方案后，优先开发 `parse_metrics.py` (中文 Prompt) 和 API。
2. 开发前端 Keep 编辑面板。