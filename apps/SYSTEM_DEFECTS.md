# 系统缺陷与架构演进记录 (Technical Debt & Roadmap)

本文档用于记录当前系统存在的逻辑缺陷、被搁置的架构问题以及未来的解决方案草案。

## 1. 产品记忆与偏好切换 (Product Preference Context)

### 问题描述 (The Problem)
目前的 `product_library.jsonl` 仅包含产品的静态元数据（Brand, Name, Nutrients）和 `created_at`。系统缺乏对“使用上下文”的追踪。

**具体表现：**
1.  **缺乏“最后使用时间” (`last_used_at`)**：系统不知道用户最近一次吃“脱脂奶”到底是选了 Brand A 还是 Brand B。
2.  **缺乏“类型聚合” (`category` / `standard_name`)**：系统难以将 "荷高脱脂奶" 和 "德亚脱脂奶" 归类为同一个 "Generic Skim Milk" 概念，从而无法在该概念下进行偏好仲裁。

### 用户场景 (Scenario)
1.  用户录入 Brand A (脱脂奶)。 -> 系统默认 Brand A。
2.  用户录入 Brand B (脱脂奶，营养不同)。 -> 系统应当感知到偏好变更为 Brand B。
3.  用户再次显式录入 Brand A (例如扫了 Brand A 的码，或明确说了 Brand A)。 -> **系统偏好应当切回 Brand A**。
4.  用户下次只说 "喝了脱脂奶" (Generic Input)。 -> **系统应当自动通过 Brand A 的数据进行计算** (因为 A 是 Latest Used)。

### 拟定解决方案 (Proposed Solution)

#### A. 数据结构变更
在 `product_library.jsonl` 中引入动态字段：
*   `last_used_at` (Datetime): 每次该产品被用于 Daily Record 时更新此时间。
*   `access_count` (Integer): 使用频率计数（可选，辅助权重）。
*   `alias_group` / `standard_name` (String): (可选) 用于显式关联 Generic Name，如 "脱脂奶"。

#### B. 读写逻辑变更 (LRU Strategy)
1.  **写入/更新时**：
    *   当 `RecordService.save_diet_record` 保存一条记录时，不仅写入 Ledger，还应**异步触达 Product Library**。
    *   找到本次记录中使用的产品（通过 Brand+Name 匹配），**更新其 `last_used_at` 为当前时间**。
2.  **读取/检索时 (Prompt Context)**：
    *   当构建 Prompt (`get_product_memories`) 时，不再仅仅随机或按创建时间提取。
    *   **策略调整**：按 `last_used_at` 倒序排列。
    *   **效果**：LLM 会首先看到最近使用的那个“脱脂奶”，从而倾向于使用它的数据作为 Generic Input 的默认值。

---

## 2. 多时区与时间上下文 (Time Context) - [STATUS: ON HOLD]

### 问题描述
当前系统强依赖宿主机的系统时间 (`datetime.now()`)，导致以下问题：
1.  **跨时区无法对其**：若服务器在 UTC+0，用户在 UTC+8，用户说的“昨天”和服务器理解的“昨天”可能相差一整天。
2.  **补录偏移**：补录历史数据时，文件名归档依赖于具体的时区切分点。

### 暂时结论
由于目前主要为单机个人使用，且通过 Mock 默认时区或 Context Provider 的方式进行解耦涉及过度设计，**该议题暂时搁置**。
目前系统默认：**用户时区 = 宿主机系统时区**。

---

## 3. 历史数据兼容性 (Legacy Data Compatibility)

### 已知状态
*   所有 Ledger 和 Keep 记录已通过 Replace Tool 强制补全了 `occurred_at` 字段。
*   代码中移除了针对无 `occurred_at` 数据的复杂回退逻辑。

### 剩余风险
*   若未来手动修改 JSONL 文件且遗漏 `occurred_at`，可能导致该记录在 `get_unified_records_range` 中被丢弃。
*   **规范**：任何入库工具必须保证 `occurred_at` 的存在。

---

## 4. Keep 数据的语义消歧 (Semantic Ambiguity)

### 问题描述
Keep 数据记录中包含 `date_str` ("1月1日") 等非结构化或半结构化日期，依赖 API 调用时的年份上下文。若在跨年场景下补录（例如 2026年1月补录 2025年12月的数据），简单的字符串匹配可能导致年份错误。

### 拟定方向
*   LLM 解析阶段需注入明确的 `current_year` 或 `target_year` 上下文。
*   在 `occurred_at` 系统完善后，尽量依赖 `occurred_at` 作为唯一真理，忽略原始文本中的模糊日期。
