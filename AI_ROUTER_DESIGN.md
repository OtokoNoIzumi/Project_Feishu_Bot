# AI辅助智能路由系统设计文档 v2.0

## 📋 项目重新定位

### 核心目标
将AI辅助意图识别能力**整合到现有飞书机器人架构**，支持：
- 自然语言→业务功能的智能路由
- 多知识库的笔记记录与查询系统
- 可撤销的数据操作机制
- 现有Services体系的无缝扩展

### MVP定义修正
**MVP = 整体架构完整规划 → 按可验收模块逐步实施**
- 阶段1：AI Router核心服务 + 基础Note模块
- 阶段2：多知识库管理 + RAG查询
- 阶段3：可撤销缓存机制 + 高级上下文
- 阶段4：外部平台集成 + 界面优化

---

## 🏗️ 与现有架构的整合设计

### 现有架构分析
当前系统已有完善的四层架构：
```
FeishuAdapter (前端适配器)
    ↓
MessageProcessor (业务处理器)
    ↓
AppController (应用控制器)
    ↓
Services (服务层): config, cache, audio, image, scheduler, notion
```

### AI Router的整合位置
**在MessageProcessor中增加AI Router能力**，**在Services中增加新服务**：

```
FeishuAdapter (无需改动)
    ↓
MessageProcessor (增加AI Router逻辑)
    ↓
AppController (服务注册扩展)
    ↓
Services (新增): llm_service, router_service, note_service, rag_service
```

### 新增Services设计

#### 1. LLMService (Module/Services/llm/)
```python
class LLMService:
    """Google Gemini集成服务"""
    def __init__(self, config_service):
        self.api_key = config_service.get_env("GEMINI_API_KEY")

    def analyze_intent(self, user_input: str, available_modules: Dict) -> IntentResult
    def generate_prompt(self, modules_info: Dict) -> str
    def get_status(self) -> Dict
```

#### 2. RouterService (Module/Services/router/)
```python
class RouterService:
    """智能路由服务 - 整合快捷指令和AI识别"""
    def __init__(self, app_controller):
        self.llm_service = app_controller.get_service('llm')
        self.note_service = app_controller.get_service('note')
        self.modules_config = self.load_modules_config()

    def route_message(self, context: MessageContext) -> RouteResult
    def parse_shortcuts(self, user_input: str) -> Optional[ShortcutMatch]
    def load_modules_config(self) -> Dict
```

#### 3. NoteService (Module/Services/note/)
```python
class NoteService:
    """笔记和知识库管理服务 - 多用户架构"""
    def __init__(self, app_controller):
        self.cache_service = app_controller.get_service('cache')
        self.config_service = app_controller.get_service('config')
        self.data_root = self.config_service.get("data_root", "/data")

    def record_note(self, user_id: str, content: str, kb_name: str = "default") -> ProcessResult
    def query_notes(self, user_id: str, query: str, kb_names: List[str] = None) -> QueryResult
    def manage_knowledge_base(self, user_id: str, kb_name: str, action: str) -> bool
    def get_user_data_path(self, user_id: str) -> str
    def ensure_user_directories(self, user_id: str) -> bool
```

#### 4. ConfirmationService (Module/Services/confirmation/)
```python
class ConfirmationService:
    """可撤销操作和高效编辑服务"""
    def __init__(self, app_controller):
        self.cache_service = app_controller.get_service('cache')

    def create_confirmation(self, user_id: str, operation: Dict) -> ConfirmationRecord
    def get_confirmation(self, confirmation_id: str) -> Optional[ConfirmationRecord]
    def update_confirmation(self, confirmation_id: str, new_data: Dict) -> bool
    def execute_confirmation(self, confirmation_id: str) -> ProcessResult
    def cancel_confirmation(self, confirmation_id: str) -> bool
```

#### 4. RAGService (Module/Services/rag/)
```python
class RAGService:
    """RAG检索增强生成服务"""
    def __init__(self, config_service):
        self.vector_store_path = config_service.get("rag_vector_store_path")
        self.embeddings = self.init_embeddings()

    def build_index(self, documents: List[Document]) -> bool
    def search(self, query: str, kb_filter: Dict = None) -> List[SearchResult]
    def update_documents(self, documents: List[Document]) -> bool
```

---

## 📚 Note模块多知识库设计

### 知识库架构 (多用户设计)
```
/data/
├── users/
│   ├── {user_id_1}/
│   │   ├── knowledge_bases/
│   │   │   ├── default/      # 该用户的默认知识库
│   │   │   ├── work/         # 该用户的工作知识库
│   │   │   ├── personal/     # 该用户的个人知识库
│   │   │   └── {custom}/     # 该用户的自定义知识库
│   │   ├── config/
│   │   │   ├── knowledge_bases.json
│   │   │   └── preferences.json
│   │   └── cache/
│   │       └── pending_operations.json
│   └── {user_id_2}/
│       └── ... (同样结构)
└── shared/                   # 共享资源（可选）
    └── templates/
```

### 知识库配置 (/config/knowledge_bases.json)
```json
{
  "knowledge_bases": {
    "default": {
      "name": "通用知识库",
      "description": "默认的通用笔记存储",
      "storage_path": "/data/knowledge_bases/default",
      "enabled": true,
      "auto_category": true,
      "rag_enabled": true
    },
    "work": {
      "name": "工作知识库",
      "description": "工作相关的笔记和任务",
      "storage_path": "/data/knowledge_bases/work",
      "enabled": true,
      "keywords": ["会议", "项目", "任务", "工作"],
      "rag_enabled": true
    },
    "personal": {
      "name": "个人知识库",
      "description": "个人生活、想法记录",
      "storage_path": "/data/knowledge_bases/personal",
      "enabled": true,
      "keywords": ["生活", "想法", "心情", "日记"],
      "rag_enabled": true,
      "privacy": true
    }
  },
  "routing_rules": {
    "auto_detect": true,
    "default_kb": "default",
    "keyword_routing": true,
    "llm_classification": true
  }
}
```

### 多知识库交互设计
```
用户输入: "jl 今天的会议很有收获"
    ↓
RouterService识别: 记录笔记
    ↓
NoteService分类: 检测到"会议"关键词 → work知识库
    ↓
存储: /data/knowledge_bases/work/2024-01/meeting_notes_001.md
    ↓
RAGService: 更新work知识库的向量索引
```

### 查询跨知识库支持
```python
# 单知识库查询
cx work 上周的会议记录

# 多知识库查询
cx work,personal 关于项目的所有想法

# 全库查询
cx * 关于AI的所有内容
```

---

## 🔄 整合到MessageProcessor的路由逻辑

### 当前MessageProcessor._process_text_message()的修改
```python
def _process_text_message(self, context: MessageContext) -> ProcessResult:
    user_msg = context.content

    # 1. 优先处理现有精确匹配（保持兼容性）
    exact_result = self._try_existing_exact_matches(user_msg)
    if exact_result:
        return exact_result

    # 2. 新增AI Router处理
    if self.app_controller and self.app_controller.get_service('router'):
        router_service = self.app_controller.get_service('router')
        route_result = router_service.route_message(context)

        if route_result.success:
            return self._execute_routed_action(route_result)

    # 3. 兜底处理（现有逻辑）
    return ProcessResult.success_result("text", {
        "text": f"收到你发送的消息：{user_msg}"
    })
```

### RouterService路由逻辑
```python
def route_message(self, context: MessageContext) -> RouteResult:
    user_input = context.content

    # 1. 快捷指令匹配 (优先级最高)
    shortcut_match = self.parse_shortcuts(user_input)
    if shortcut_match:
        return RouteResult.from_shortcut(shortcut_match)

    # 2. 特殊前缀处理 (领域开关)
    domain_match = self.parse_domain_prefix(user_input)
    if domain_match:
        return RouteResult.from_domain(domain_match)

    # 3. AI意图识别
    intent_result = self.llm_service.analyze_intent(
        user_input,
        self.get_available_modules()
    )

    if intent_result.confidence > self.get_threshold(intent_result.module_name):
        return RouteResult.from_intent(intent_result)

    # 4. 无匹配
    return RouteResult.no_match()
```

---

## 📊 模块配置与注册 (/config/ai_modules.json)

```json
{
  "modules": {
    "note_record": {
      "name": "笔记记录",
      "shortcuts": ["jl", "note", "记录"],
      "description": "记录想法、灵感、知识点到指定知识库",
      "confidence_threshold": 0.6,
      "has_side_effects": true,
      "keywords": ["记录", "笔记", "保存", "写下"],
      "handler": "note_service.record_note",
      "parameters": {
        "content": {"type": "string", "required": true},
        "knowledge_base": {"type": "string", "default": "auto"}
      }
    },
    "note_query": {
      "name": "笔记查询",
      "shortcuts": ["cx", "query", "查询"],
      "description": "从知识库检索相关信息",
      "confidence_threshold": 0.5,
      "has_side_effects": false,
      "keywords": ["查询", "找", "搜索", "检索"],
      "handler": "note_service.query_notes",
      "parameters": {
        "query": {"type": "string", "required": true},
        "knowledge_bases": {"type": "array", "default": ["*"]}
      }
    },
    "kb_manage": {
      "name": "知识库管理",
      "shortcuts": ["kb", "知识库"],
      "description": "创建、删除、配置知识库",
      "confidence_threshold": 0.7,
      "has_side_effects": true,
      "keywords": ["知识库", "创建", "删除", "管理"],
      "handler": "note_service.manage_knowledge_base"
    }
  },
  "tools": {
    "tts": {
      "shortcuts": ["py", "配音"],
      "handler": "existing_tts_handler"
    },
    "image_gen": {
      "shortcuts": ["st", "生图"],
      "handler": "existing_image_handler"
    }
  },
  "domain_triggers": {
    "tavern_brawl": {
      "one_time_prefix": "酒馆/",
      "persistent_prefix": "酒馆@",
      "exit_keyword": "退出酒馆",
      "knowledge_base": "gaming"
    }
  }
}
```

---

## 🚀 分阶段实施计划

### 阶段1：AI Router核心服务 + 可撤销编辑机制 (可验收: 智能路由和高效编辑生效)
**目标**：用户可以通过自然语言触发笔记记录和查询，支持高效的可撤销编辑

**实施内容**：
1. 创建LLMService (Gemini集成)
2. 创建RouterService (快捷指令+AI识别)
3. 创建基础NoteService (多用户架构，单知识库)
4. 创建ConfirmationService (可撤销编辑机制)
5. 修改MessageProcessor集成路由逻辑
6. 设计高效的飞书编辑卡片交互
7. 在AppController中注册新服务

**验收标准**：
- `jl 今天学到了XXX` → 显示确认卡片，支持快速编辑
- 确认卡片交互流畅，编辑步骤简化
- `cx 昨天记录了什么` → 成功查询返回（含用户隔离）
- `py 测试语音` → 原有TTS功能正常

### 阶段2：多知识库管理 (可验收: 智能分类生效)
**目标**：笔记可以自动分类到不同知识库，支持跨库查询

**实施内容**：
1. 扩展NoteService支持多知识库
2. 创建RAGService处理向量检索
3. 实现knowledge_bases.json配置管理
4. 增加知识库管理指令

**验收标准**：
- `jl 今天开会讨论了XXX` → 自动分类到work知识库
- `cx work 上周会议` → 只在work库中查询
- `kb 创建 gaming` → 成功创建新知识库

### 阶段3：可撤销机制 + 高级上下文 (可验收: 交互体验提升)
**目标**：提供可撤销的数据操作和领域切换

**实施内容**：
1. 在RouterService中实现ConfirmationManager
2. 扩展CacheService支持操作缓存
3. 实现领域前缀触发机制
4. 增加飞书卡片交互支持

**验收标准**：
- 记录操作显示确认卡片，支持编辑/撤销
- `酒馆/查询XXX卡` → 进入游戏领域查询
- 30分钟自动提交缓存操作

### 阶段4：外部平台集成 + Markdown文档支持 (可验收: 编辑界面可用)
**目标**：支持本地Markdown和飞书文档/Notion的双向同步

**实施内容**：
1. 实现本地Markdown文件管理
2. 扩展RAGService支持外部文档
3. 实现文档变更监控和同步
4. 增加导入/导出功能
5. 优化用户界面和体验

**验收标准**：
- 支持本地Markdown文件编辑和同步
- 可以从飞书文档导入笔记到知识库
- 修改飞书文档自动更新RAG索引
- 支持导出知识库到外部平台

---

## 📝 关键问题确认

### 1. 架构整合确认
- **新服务注册**：在Module/Services/__init__.py中添加新服务
- **AppController扩展**：在auto_register_services()中注册AI Router相关服务
- **MessageProcessor修改**：在_process_text_message()中集成路由逻辑
- **配置文件**：新增/config/ai_modules.json和/config/knowledge_bases.json

### 2. Note模块多知识库设计确认
- **目录结构**：/data/knowledge_bases/{kb_name}/
- **自动分类**：基于关键词+LLM的双重分类机制
- **跨库查询**：支持指定单库、多库、全库查询
- **权限管理**：支持私有知识库设置

### 3. 实施优先级确认
- **阶段1优先**：先实现基本的AI路由和单知识库功能
- **逐步验收**：每个阶段都有明确的功能验收标准
- **向后兼容**：不影响现有功能，新功能是增量添加

---

## 🤔 待你确认的设计选择

1. **服务注册位置**：新服务注册在Module/Services/下是否合适？
2. **配置文件格式**：使用JSON而非YAML是否OK？
3. **多知识库设计**：自动分类+手动指定的混合模式是否符合需求？
4. **分阶段计划**：4个阶段的划分和验收标准是否合理？
5. **历史思路整合**：是否采用second_brain_raw中的BaseModule架构？

---

## 🎨 高效编辑卡片设计 (阶段1重点)

### 核心要求
- **交互高效**：最少步骤完成编辑操作
- **即时反馈**：编辑结果实时显示
- **可撤销**：支持快速撤销和重做
- **智能建议**：AI辅助内容优化

### 初步卡片设计思路 (详细设计待细聊)
```
📝 AI识别结果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
记录到: 工作知识库 | 置信度: 85%

内容: [今天的会议很有收获，讨论了新项目的技术方案]
      ↑ 点击直接编辑，支持快速修改

🔧 [直接确认] [快速编辑] [改分类] [取消]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**关键特性**：
1. **内容可直接点击编辑**（无需额外"编辑"按钮）
2. **分类可快速切换**（下拉选择）
3. **一键确认/取消**
4. **30分钟自动确认**（避免忘记）

---

## ✅ 设计确认完成，准备开发

基于你的反馈，设计已完善：

1. ✅ **整体架构**：整合到现有Services，按最佳实践处理
2. ✅ **多用户支持**：所有数据存储都按用户隔离
3. ✅ **可撤销编辑**：阶段1重点，高效交互设计
4. ✅ **MVP规划**：分4阶段，前2阶段不含外部文档
5. ✅ **现有兼容**：优先使用验证过的组件

**下一步**：开始阶段1具体开发 - 创建新的Services并集成到MessageProcessor！