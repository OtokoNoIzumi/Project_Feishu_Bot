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

### 2.5 缓存策略补充 (Smart Caching)
*来源：diet_bot_specs_v2.md*
(保留技术参考，但需注意 Web 前端已自行处理部分 State, Server Cache 主要用于 Feishu Card 场景)

---

## 3. Web App 架构与现状 (Web App Architecture & Status)

> *Last Updated: 2026-01-16*
> 本节反映当前实际代码库状态，包含纯静态架构与模块化设计。

### 3.1 核心架构 (As-Built)

采用了 **纯静态 HTML + 模块化 JavaScript (ESM)** 架构，完全解耦前端与后端。

*   **技术栈**: Vanilla JS (ES6 Modules), CSS (Variables), Clerk SDK (Auth), ECharts (Viz).
*   **部署**: GitHub Pages (Client) + FastAPI (Server).
*   **通信**: `api.js` 封装 Fetch 请求，自动注入 Clerk JWT Token。
*   **路由**: 简单的 SPA (Single Page Application) 逻辑，通过 `dashboard.js` 切换 View (Analysis / Profile)。

#### 目录结构 (Current)
```
Project_Feishu_Bot/
├── web/                      # 纯静态前端
│   ├── index.html            # 入口页 (登录/Landing)
│   ├── dashboard.html        # 主界面 (Chat + Result Panel + Profile)
│   ├── config.js             # 环境配置
│   ├── css/
│   │   ├── styles.css        # 基础样式 + Variables
│   │   ├── dashboard.css     # 核心布局与组件样式
│   │   └── icons/            # 静态资源
│   └── js/
│       ├── app.js            # Index页面逻辑
│       ├── auth.js           # Clerk 鉴权封装
│       ├── api.js            # Axios/Fetch 封装 (JWT Header)
│       ├── dashboard.js      # 主控制器 (Delegator)
│       ├── modules/          # 业务逻辑拆分
│       │   ├── analysis.js       # 分析流程 (API调用/轮询)
│       │   ├── diet-render.js    # 饮食卡片渲染 (DOM操作)
│       │   ├── diet-edit.js      # 饮食数据编辑与交互
│       │   ├── keep-render.js    # Keep 渲染
│       │   ├── nutrition-chart.js # ECharts 图表封装
│       │   ├── parser.js         # 后端数据适配层
│       │   ├── profile.js        # Profile 逻辑
│       │   ├── session.js        # 会话与消息流管理
│       │   └── storage.js        # 历史记录管理
│       └── utils/            # 工具函数
│           ├── energy.js         # kJ/kcal 转换
│           ├── image.js          # 图片压缩/预览/Hash
│           ├── text.js           # Markdown 渲染
│           └── icons.js          # Icon 组件映射
└── ...
```

### 3.2 已完成核心功能 (Done)

#### 基础框架
- [x] **Clerk 登录集成**: 纯 JS SDK 实现，支持 Google/One-Time Code。
- [x] **三栏布局**:
  - 左侧: 历史记录 (Session Title)。
  - 中间: 确认面板 (Result Panel)，移动端支持底部抽屉模式 (Bottom Sheet)。
  - 右侧: 对话与输入区，常驻底部。
- [x] **模块化重构**: Dashboard 拆分为 9+ 个子模块，逻辑清晰。

#### Diet 模块
- [x] **图文多模态分析**: 支持图片/文本/混合输入。
- [x] **交互式编辑**:
  - 菜品/食材名称、重量、营养素均可编辑。
  - **启用/禁用 (Checkbox)**: 实时重新计算总热量。
  - **等等比缩放 (Scale)**: 修改重量自动按比例调整营养素。
- [x] **数据可视化 (FEAT-001)**: ECharts 堆叠图，实时对比 本次分析 vs 今日已摄入 vs 每日目标。
- [x] **智能建议 (Advice)**: 自动生成建议，支持折叠 (FEAT-004)。

#### Keep 模块
- [x] **基础渲染**: 展示 Scale (体脂秤) 和 Dimensions (围度) 数据。
- [x] **多事件保存**: 修复了数据污染问题，支持复杂场景保存。

#### Profile
- [x] **基础配置**: 支持设置 Diet/Keep 目标、能量单位 (kJ/kcal)。

#### 最近优化 (Recent Polish) - *2026-01-20*
- [x] **性能优化**: 全局脚本增加 `defer` 属性，解决白屏阻塞问题。
- [x] **视觉微调**: 
  - 字体栈优化：西文 Lora + 中文微软雅黑，平衡美感与可读性。
  - 输入框样式修复：强制继承字体，解决默认 sans-serif 突兀问题。
  - 营养图表：增加 NRV 参考值 (默认 2000kcal/60g蛋白等)，解决无目标时的空图显示问题。
- [x] **逻辑修正**:
  - **Profile Prompt**: 严禁 AI 在 `user_info` 中夹带建议，仅记录事实。
  - **Context Provider**: 修复饮食建议 (Advice) 读取旧 profile.json 的问题，正确挂钩真实用户配置。

---

## 4. 废弃或已合并章节 (Merged/Deprecated)
### 4.1 支付与商业化 (Payment & MoR)
*   **阶段一：验证期 (Seed)**
    *   **策略**: 手动转账 (微信/支付宝) -> Admin 面板手动开通权限。
    *   *优势*: 零手续费，直接接触核心用户，验证需求。
*   **阶段二：规模化 (Scale)**
    *   **策略**: 使用 **Merchant of Record (MoR)** 平台，如 **LemonSqueezy**.
    *   *优势*: 平台作为“经销商”处理全球税务 (Tax compliant)，你只需接收结算款。相比 Stripe 纯网关模式，MoR 更适合独立开发者（无需在早期注册复杂的海外公司实体）。
*   **模板参考**:
    *   **ShipFast**: 包含 Next.js + Tailwind + Stripe/LemonSqueezy 的成熟脚手架。
    *   **Makerkit**: 功能更全的 SaaS Starter。

*(原 Section 3.4-3.10 的规划内容已大部分实现或并入 3.1/3.2，此处保留标题占位，内容已归档)*

**(原 Section 3.6 用户关联)**: 采用方案 A (手动映射) 运行中。
**方案 B：统一账户表 (长期)**
*   **原理**: 数据库新建 `User` 表，包含 `id (uuid)`, `clerk_id`, `feishu_id` 字段。
*   **操作**: 业务逻辑全部基于内部 `uuid`。登录时动态查找对应的 `uuid`。
**(原 Section 3.10 营养图表)**: 已实现为 `nutrition-chart.js`。

---

## 5. 周分析功能 (Weekly Analysis) - Diet & Keep

> *Status: MVP 2 (AI Analysis Ready)*

### 5.1 功能概述
为 Diet 和 Keep 模块提供周维度的综合分析能力，包括：
- 餐食质量分析与评分
- 下周餐食建议
- 热量校准系数估算
- 目标进度对比
- 围度变化分析
- 可视化趋势图表

### 5.2 目录结构
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

### 5.3 MVP 拆分与进度

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

### 5.4 数据源与条件

| 数据 | 来源 | 采集逻辑 |
|-----|------|---------|
| Diet Records | `ledger_{date}.jsonl` | 周区间内所有文件 |
| Dish Library | `dish_library.jsonl` | 取最新100条 |
| Scale Records | `scale_{yyyy_mm}.jsonl` | 周区间内的记录 |
| Sleep Records | `sleep_{yyyy_mm}.jsonl` | 周区间内的记录 |
| Dimensions | `dimensions_{yyyy_mm}.jsonl` | 周内 + baseline(周前最后一条) |
| Profile | `profile.json` | 用户目标配置 |
| Preferences | `preferences.json` | 🆕 个性化饮食偏好 |

### 5.5 分析触发条件

| 分析项 | 触发条件 |
|-------|---------|
| 餐食质量分析 | `len(diet_records) > 0` |
| 下周餐食建议 | `len(diet_records) > 0 and len(dish_library) > 0` |
| 热量校准 | `len(diet_records) >= 3 and len(scale_records) >= 2` |
| 目标进度 | `profile is not None` |
| 围度分析 | 至少2个不同日期的围度数据 |

### 5.6 个性化偏好配置
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

## 6. Keep 模块升级与数据治理方案 (Keep Upgrade)

针对现有 Keep 数据结构简单、新旧数据重叠、以及引入详细围度 (Body Metrics) 后的数据治理挑战，制定本升级方案。

### 6.1 核心挑战

1.  **数据重叠**：`scale` (体脂秤), `dimensions` (基础围度), `metrics` (20+详细围度) 存在字段交叉（如体重、腰围）。
2.  **Schema 割裂**：Keep 原有 Schema 字段命名 (`chest_cm`) 与新 Schema (`bust`) 不一致。
3.  **交互限制**：Keep 目前强制要求图片，不支持纯文本/混合输入。

### 6.2 数据治理策略 (Data Governance)

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

### 6.3 开发实施方案 (Implementation Plan)

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

### 6.4 示例 Unified Prompt (Chinese)

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

### 6.5 下一步动作
1. 确认上述方案后，优先开发 `parse_metrics.py` (中文 Prompt) 和 API。
2. 开发前端 Keep 编辑面板。

---

## 7. 实施路线图 (Execution Roadmap)

> *Last Updated: 2026-01-17*
> 按照“发布到生产环境”的优先级进行排序。请按顺序执行。

### Phase 1: 核心基石 (Foundation)
*目标：确保数据不丢失，服务可部署，访问有门禁。*

1.  **[High] Profile 云端持久化 (Profile Persistence)** ✅ 已完成 (前端)
    *   *Task*: 开发 `GET/POST /api/user/profile` 接口，前端 `profile.js` 改为从后端读写。
    *   *Value*: 用户刷新/换设备配置不丢失，是所有个性化分析的基础。
    *   *User Idea*: 增加 profile 的保存，读取，快速选择，以及单独运转利用右侧llm对话的 profile 编辑模式。
    *   *Agent Note*: 当前 `profile.js` 已有基础结构。需要：
        *   后端增加 API 支持 Profile 预设 (如 "减脂期", "增肌期")。
        *   前端增加 Profile 下拉切换器。
        *   右侧面板完全复用 Profile 编辑器组件，支持脱离 Chat 上下文的独立路由。    

2.  **[High] 简易邀请码与权限控制 (Auth & Gatekeeping)**
    *   *Task*: 后端增加 `invitation_codes.json` 白名单机制。无码用户仅能试用 3 天或 5 条。
    *   *Value*: 保护 API Token，为后续收费做准备。
2.1. **登录方式扩展 (Clerk Alternatives/Codes)**
    *   *User Idea*: 了解 clerk 的一些备选登陆方式，考虑前期的用户注册用邀请码或者 code 做必备的功能激活，没有 code 的账号就只能试用 3 天。
    *   *Agent Note*:
        *   Clerk 支持 "Allowlist" 或 Custom Flow。
        *   更简单的做法：App 逻辑层限制。User 登录后，检查 DB 中是否有 Active Subscription 或 Valid Invitation Code。如果没有，限制 Usage Count 或 Time。
3.  **[High] 生产环境部署架构 (Deployment Setup)**
    *   *Task*: 配置 `docker-compose` 或 Nginx，统一反代 前端静态文件 (`/`) 和 后端 API (`/api`)。
    *   *Value*: 解决跨域与 HTTPS 问题，摆脱本地运行限制。
    *   *User Idea*: 为啥不尝试做github上试试？总之我虽然弄过ssl的api证书，但确实没直接弄过网站……



### Phase 2: 交互重构 (Interaction & IA)
*目标：像一个成熟的 Chatbot，而非文件编辑器。*

4.  **[High] 左侧双层导航 (Sidebar Tree View)**
    *   *Task*: 重构 Sidebar。
        *   Level 1: **Sessions** (以时间/话题命名的会话)。
        *   Level 2: **Cards** (展开显示该会话内的“早餐”、“Keep记录”等卡片快捷入口)。
    *   *Value*: 解决“找记录难”的问题。
        *   **两级结构 (Tree View)**: 一级是 Session (对话)，二级是 Session 内生成的 Analysis Cards (分析结果)。
        *   **卡片状态**: 二级菜单中的卡片应显示状态（如：✅ 已保存, ⏳ 待处理, 📝 草稿），不仅仅是标题。
        *   **目的**: 方便不翻阅冗长的 Chat History 就能快速定位到具体的“mm-dd早饭”、“午饭”卡片进行编辑。
5.  **[Medium] 独立 Advice 模式 (Independent Mode)**
    *   *Task*: 右侧面板增加“顾问模式”开关，允许脱离特定卡片进行自由问答。
    *   *Value*: 增强 AI 的陪伴感和顾问属性。
    *   *User Idea*: 增加独立的 advice 模式并调优 advice 的上下文，现在默认的 advice 组装的信息太少了，要向 weekly 看齐。另外analyze的部分信息也没传递到advice中，比如image info。
    每天早上的日报（如果有权限）额外做一个简易的weekly的全天分析和规划，要考虑昨天的进食，有血糖数据还要提取血糖数据对比分析。
    *   *Agent Note*:
        *   需要从 Backend 拉取更长周期的 History (e.g., past 7 days) 注入 Prompt。
        *   Frontend 增加 "Ask Advice" 独立入口——具体来说目前就是没有选中diet/keep的时候，不依赖特定 Image Card。    


6.  **[Medium] 图片缩略图策略 (Thumbnail Strategy)**
    *   *Task*: 后端接收图片生成 300px 缩略图持久化，原图依赖 Gemini 48h 有效期。Chat History 仅加载缩略图。
    *   *Value*: 降低服务器存储成本，提升加载速度。

7.  **[Medium] 错误状态恢复 (Error Recovery)**
    *   *Task*: 分析失败时保留用户上传的图和文字，允许修改 Note 后重试。
    *   *Value*: 避免用户挫败感。
    *   *User Idea*: 分析失败的时候不要展示空页面，至少把用户输入信息列出来：图片略缩图+可编辑的 user note。
    *   *Agent Note*: 优化前端错误处理流程。当 API 返回错误时，保留并显示用户已输入的 Image/Text，允许用户修改 Note 后发起 Retry，防止数据丢失。    

### Phase 3: Keep 模块闭环 (Keep Integration)
*目标：让运动数据可视化，形成正反馈。*

8.  **[High] Keep 统一编辑器 (Unified Editor)**
    *   *Task*: 实现动态切换 Scale/Dimensions/Sleep 的编辑面板 (对应 Section 6)。
    *   *Value*: 解决数据分类混乱问题。
    对围度记录要支持后端传参用户权限和数据量来区分详细数据和简略数据的不同编辑排版，详略当然要支持额外不打字才行，现在输入文字还是太麻烦。
    emoji表情的修改可以适度看看，没改也不影响MVP

9.  **[High] 数据可视化趋势卡片 (Trend Visualization)**
    *   *Task*: 在 Keep 分析结果中增加 ECharts 趋势图 (体重/体脂近7天变化)。
    *   *Value*: 提供核心情绪价值。
    *   *User Idea*: KEEP 模式也要有一个类似的 advice 步骤，不过暂时不调用 LLM，只是做一下近期数据的 echarts 图例，再另外强调一下核心变化值。
    *   *Agent Note*:
        *   编写 `keep-render.js` 扩展，增加 "Trend Card"。
        *   复用 `nutrition-chart.js` 逻辑绘制体重/围度折线图。    

10. **[Low] 历史数据批量录入 (Batch Import)**
    *   *Task*: 日历视图批量补录旧数据。
    *   *Value*: 方便老用户迁移。

### Phase 4: 体验打磨 (Polishing)
*目标：增加“高级感”和微交互。*

11. **[Medium] Loading 动态效果** (CSS Wobble/Pulse 动画)。
    *   *User Idea*: 在初始界面分析过程 loading 时，中间的 bowl 图标也要有个动态动画。可能需要拆分出 4 个图标类似 `...` 一样轮换，或者就是左右摇动那就只需要一个图。
    *   *Agent Note*: CSS Keyframe Animation 即可实现左右摇动 (`wobble`) 或 呼吸效果 (`pulse`)。不需要额外图片资源。优先尝试 CSS 动画。
12. **[Low] 贴纸交互 (Sticker Interactivity)** (点击变色/旋转)。
    *   *User Idea*: before 的 css 贴纸可以点，点了会变样式——随机？或者可以先从改倾斜开始？
    *   *Agent Note*: 实现点击事件监听，切换 CSS class (e.g., `.sticker-rotate-1`, `.sticker-color-2`) 增加趣味性。
13. **[Low] 开屏情绪价值 (Splash Screen)** (随机展示 Daily Wisdom)。
    *   *User Idea*: 开屏的基础信息，增加一些情绪价值，小标题，小哲理啥的，因为是AI收费所以直接是按账户来，先不用广告？还是说广告可以买掉？
    *   *Agent Note*: 前端 Splash Screen 增加随机文案库 ("Daily Wisdom")。付费模式可作为去广告或解锁高级文案的逻辑。
14. **[Low] 移动端细节优化** (滚动穿透/键盘遮挡修复)。

### Phase 5: 进阶功能 (Future Features)
15. **[Low] 演示模式 (Demo Mode)** (Mock Data 快速体验)。
    *   *User Idea*: 增加一个快速示例，立即用一个准备好的 diet case 来模拟生成内容。第一次生成的内容不调用 LLM 而是预设好的。如果不麻烦也要过一下等待的感觉比如各 10 秒，重新分析或生成建议再真的调用。
    *   *Agent Note*:
        *   在 `js/modules/analysis.js` 中增加 `mockAnalysis` flag。
        *   预埋一份完整的 JSON Response (包含 Image Hash, Parsed Data)。
        *   使用 `setTimeout` 模拟网络延迟和 Step 动画。
        *   对新用户（无 History）显示 "Try Demo" 按钮。

16. **[Low] 热量校准算法 (Calorie Calibration)** (Weekly Analysis MVP3)。
17. **[Low] 营养标签库 (Product Library Dropdown)**。
18. **营养标签产品名下拉选择 (FEAT-002)**
    *   *User Idea*: 在编辑营养标签时，产品名称支持下拉选择 (Product Library)。
    *   *Agent Note*: 需调用 API 获取产品库数据，支持模糊搜索，提升录入效率。
19. **get_product_memories 重构 (REFACTOR-002)**
    *   *User Idea*: 优化产品记忆的读取逻辑与数据结构。
    *   *Agent Note*: 后端 Logic 层重构，确保数据结构的一致性和扩展性。    
20. **[Low] 快照保存 (Label Snapshot)**。
21.  **时区 (Timezone) 深度集成**
    *   *User Idea*: 根据 profile 的时区修改后端的属性，但这个似乎有后遗症，只是先记录一下。
    *   *Agent Note*: 复杂点在于 `datetime` 对象在 Python 中的 `tzinfo` 处理。建议：后端统一存储 UTC，仅在 Context 组装给 LLM 时、以及前端渲染时转换为 User Timezone。
22.  **血糖记录与文件上传**
    *   *User Idea*: 增加血糖记录的上传功能，xlsx 直接传和覆盖，后续整合到 advice 的分析中——血糖分析模式或许可以做一个额外的收费 feature。
    *   *Agent Note*:
        *   Backend: 增加 Excel Parser (`pandas` or `openpyxl`)。
        *   Storage: 存为 `blood_glucose_{month}.jsonl`。
        *   Analysis: 将血糖波动数据 feed 给 LLM 寻找与 Diet 的关联。
23. **热量校准与代谢反推 (Calorie Calibration Algorithm)**
    *   *User Idea*: 回归算法计算体重变化和热量差值反推基本值？
    *   *Agent Note*: 属于 Weekly Analysis 的 MVP3 (Calorie Calibration) 核心功能。
        *   算法: `(Intake - TDEE) / 7700 ≈ Weight Change`。
        *   进阶: 使用线性回归 (Linear Regression) 分析近 2-4 周的数据，动态计算用户的实际代谢适应系数 (Adaptive TDEE)，而非死板套用公式。