# 飞书机器人项目变更日志

> **说明**: 本文档记录项目的重要变更、架构演进和开发里程碑。采用语义化版本控制，按时间倒序排列。

---

## [v3.1.0] - 2025-01-03 (堆栈分析架构优化)

### 🎯 **重大架构优化**
- **堆栈层次优化**: 通过深度分析将业务堆栈从15层减少到11层(减少26.7%)
- **概念冗余消除**: operation_type重复存储从5重减少到3重(减少40%)
- **消息转换层优化**: 移除metadata重复存储和硬编码字段

### ✨ **新增技术特性**
- **UI消息绑定机制**: 新增卡片消息与操作ID的关联机制
- **响应类型语义优化**: admin_card → admin_card_send，操作意图更明确
- **配置缓存机制**: 添加_config_cache减少重复配置查询
- **参数命名规范化**: operation_data → business_data，概念更清晰

### 🔧 **业务流程完善**
- **堆栈分析文档化**: 建立变量级精确分析的标准化流程
- **架构比较分析**: 量化改进效果和识别进一步优化方向
- **技术债务管理**: 建立分级的技术债务清单和处理计划

### 📚 **文档更新**
- 新增 `CARD_STACK_ANALYSIS_VER2.md` - 优化后堆栈分析
- 新增 `CARD_STACK_COMPARISON_ANALYSIS.md` - 版本对比和优化建议
- 更新架构完成度评估: 68% → 82% (提升14个百分点)

### 🎯 **优化成果**
- **开发效率**: 概念清晰化降低理解成本
- **维护性**: 冗余减少简化修改流程
- **扩展性**: UI绑定机制支持多种前端
- **稳定性**: 错误处理装饰器统一异常管理

---

## [v3.0.0] - 2025-01-03 (配置驱动卡片架构完全实现)

### 🎯 **重大架构升级**
- **配置驱动架构实现**: 完成从配置化关联到完全配置驱动的架构升级
- **自动注册机制**: 实现卡片管理器的自动发现和注册，支持零代码扩展
- **插件化架构**: 每个卡片管理器都是独立插件，支持热插拔

### ✨ **新增核心组件**
- 新增 `Module/Services/card_business_mapping_service.py` - 配置映射服务
- 重构 `Module/Adapters/feishu/cards/card_registry.py` - 统一基类和注册表
- 优化 `cards_business_mapping.json` - 双层配置文件架构

### 🔧 **卡片管理器重构**
- **BaseCardManager**: 统一的卡片管理器基类，标准化接口
- **BilibiliCardManager**: B站视频卡片，支持主视频+附加列表
- **UserUpdateCardManager**: 用户更新卡片，交互式类型选择
- **AdsUpdateCardManager**: 广告更新卡片，时间编辑器功能

### 🛠️ **技术特性完善**
- **装饰器安全体系**: `@card_build_safe`, `@card_operation_safe`, `@message_conversion_safe`
- **常量统一管理**: 统一的 `CardActions`, `ResponseTypes`, `CardConfigKeys`
- **配置验证机制**: 启动时自动验证配置文件和管理器状态

### 📚 **文档完善**
- 全面重写 `CARD_PLUGIN_GUIDE.md` - 配置驱动开发指南
- 新增 `CARD_MODULE_ARCHITECTURE.md` - 卡片模块架构总结
- 更新 `TECHNICAL_ARCHITECTURE_REFERENCE.md` - 技术架构参考

### 🎯 **架构优势**
- **零硬编码**: 所有配置集中在JSON文件中
- **热插拔**: 添加新卡片类型无需修改任何代码
- **自动发现**: 系统启动自动注册所有配置的管理器
- **完全向后兼容**: 现有功能无缝升级

---

## [v2.1.0] - 2025-06-22 (配置化关联架构设计)

### 🎯 **重大架构变更**
- **配置化关联架构设计**: 完成卡片业务解耦的完整架构设计
- **硬编码问题系统性解决**: 通过`constants.py`解决9大类硬编码问题
- **文档架构重构**: 完成README和技术架构文档的全面更新

### ✨ **新增功能**
- 新增`Module/Services/constants.py`系统常量定义
- 设计`cards_business_mapping.json`配置文件架构
- 建立3个独立卡片业务的完整映射关系

### 🔧 **架构改进**
- **卡片定位明确**: 卡片作为飞书Adapter附属特性的理念确立
- **依赖方向控制**: 卡片向下调用业务，业务不依赖卡片
- **配置文件桥接**: 业务层与卡片层通过配置解耦

### 📚 **文档更新**
- 重构README.md，添加卡片架构设计章节
- 全面更新TECHNICAL_ARCHITECTURE_REFERENCE.md
- 清理文档冗余内容，提升文档质量

### 🎯 **下一版本规划**
- Phase 1: 配置文件与服务创建
- Phase 2: Business层配置化改造
- Phase 3: Adapter层路由配置化
- Phase 4: 扩展性验证与优化

---

## [v0.8.0] - 2025-06-22 (变量集中处理)

### 🔧 **代码质量提升**
- **变量集中管理**: 完成项目中硬编码变量的集中处理
- **常量定义标准化**: 建立统一的常量管理机制

### 📝 **提交记录**
- `5ea934f` 做一次变量集中的处理，算v0.8

---

## [v0.7.x] - 2025-06-21 (管理员功能扩展)

### ✨ **功能增强**
- **管理员API扩展**: 增加了另一个管理员API指令的调用
- **模块化优化**: 整体模块化进展顺利，准备进一步优化和抽象

### 📝 **提交记录**
- `d050b29` 增加了另一个管理员api指令的调用，这次模块化整体还顺利，准备再优化和抽象一些

---

## [v0.6.x] - 2025-06-20 (架构重构与质量优化)

### 🏗️ **架构重构**
- **飞书Adapter拆分**: 完成飞书adapter的模块化拆分
- **缓存层引入**: 增加缓存层和倒计时功能
- **循环依赖解决**: 解决import的循环逻辑问题

### 🔧 **代码质量**
- **质量优化**: 大量代码质量优化，通过全用例验证
- **错误修正**: 修正定时报表细节丢失问题
- **缓存用户名**: 修正缓存获取用户名的缺陷

### 📝 **主要提交**
- `aaf94f3` 更新项目文档
- `b148812` 修正下午的定时报表细节丢失的问题，AI还是坑，备份还是好
- `714d4a4` 增加缓存层和倒计时，准备修正一个card内容的问题就先同步一份到线上
- `97551a5` 优化代码质量，解决import的循环逻辑问题
- `21897a2` 完成飞书adapter的拆分，修正缓存获取用户名的缺陷
- `5d7de64` 开始准备拆分模块和调整架构

---

## [v0.5.x] - 2025-06-19 (卡片交互系统)

### 🃏 **卡片系统建立**
- **第二个卡片完成**: 完成第二个卡片功能
- **交互语言搭建**: 尝试搭建一套标准化的交互语言
- **数据绑定规范**: 建立卡片交互事件与operation_id绑定的规范

### ✨ **功能完善**
- **API卡片状态同步**: 完成API卡片状态的同步修改和配置
- **下拉菜单整合**: 整合下拉菜单的数据处理

### 📝 **主要提交**
- `6b22222` 完成api卡片状态的同步修改和配置，准备开始为了继续拓展而优化
- `278f406` 尝试整合下拉菜单的数据，后续的卡片规范应该是所有交互事件都要和后台的operation_id绑定，这样才能确保数据是打通的
- `c365bea` 完成第二个卡片，并且尝试搭建一套交互语言

---

## [v0.4.x] - 2025-06-18 (装饰器系统)

### 🎨 **装饰器架构**
- **装饰器系统建立**: 为项目引入统一的装饰器架构
- **模块装饰器整合**: 完成三个大模块的装饰器合并
- **防御代码清理**: 通过装饰器去掉多余的防御代码

### 🔧 **模块优化**
- **Service模块**: 在service模块引入装饰器
- **飞书Adapter**: 对飞书adapter增加装饰器支持
- **代码质量**: 提高代码质量，清理冗余变量

### 📝 **主要提交**
- `7e6a7d7` 合并装饰物
- `7ea604c` 更新一下装饰器，准备合并三个大模块的装饰器
- `8f57f8e` 继续添加装饰器
- `88a6140` 在service模块开始引入装饰器
- `9cf44ca` 对飞书adapter增加装饰器
- `2597553` 增加装饰器，去掉多余的防御代码

---

## [v0.3.x] - 2025-06-16~18 (业务逻辑优化)

### 🔧 **业务逻辑重构**
- **上下文迁移**: 将上下文信息迁移到业务层
- **消息结构分析**: 增加详细的消息信息结构分析
- **回复模式**: 将消息改为回复模式
- **卡片链接优化**: 优化卡片链接，手机和电脑共用按钮

### ✨ **功能增强**
- **B站卡片迁移**: 迁移B站卡片为调用模型
- **Schedule调试**: 增加schedule调试代码

### 📝 **主要提交**
- `f54750a` 稍稍提高一下代码质量，更新bili卡片样式版本（后续迁移到配置中）
- `076e3ad` 迁移B站卡片为调用模型，并完成验收，准备清理
- `4c2ef40` 优化卡片链接，现在手机和电脑可以共用一个按钮
- `565af89` 将上下文信息迁移到业务层

---

## [v0.2.x] - 2025-06-14~15 (架构拆分)

### 🏗️ **架构重构**
- **Message Processor拆分**: 拆分message_processor模块
- **Router逻辑优化**: 优化router逻辑，向正式设定靠拢
- **LLM意图识别**: 实现LLM驱动的意图识别功能

### 📝 **主要提交**
- `aef9c00` 拆分message_processor
- `0d39187` 提交一份优化过一部分router逻辑的版本，准备往正式设定上靠
- `90a9812` 提交一版至少跑通llm的意图识别，待调整意图识别的逻辑和结构

---

## [v0.1.x] - 2025-06-02~10 (项目重构)

### 🚀 **项目重构**
- **全功能重构**: 完成全功能的重构，准备合并主干
- **模块整合**: 整合各个功能模块
- **API鉴权**: 调整API鉴权功能
- **图像/TTS模块**: 完成图像模块和TTS的重构

### 🔧 **技术改进**
- **配置加载**: 修正配置加载问题
- **服务日志**: 完成服务日志检测功能
- **重连机制**: 为图像模块增加更健壮的重新链接功能

### 📝 **主要提交**
- `0359f66` 完成全功能的重构，准备做额外的功能，先合并、替换和删除老版本，然后做一次完整的代码review
- `0088633` 完成图像模块的迁移
- `1b8079c` 完成TTS的重构
- `2d50545` 开始完成服务日志的检测

---

## [v0.0.x] - 2025-02-22~05-31 (项目初始化)

### 🎉 **项目创建**
- **项目初始化**: 完成飞书机器人项目的初始化
- **基础功能**: 实现基础的消息处理、TTS、图像生成功能
- **B站集成**: 增加B站视频推荐功能
- **配置管理**: 建立环境配置管理机制

### 📝 **重要里程碑**
- `347e482` Initial commit
- `fb75933` 增加B站计时器功能
- `918a1cd` 解决点击事件（要注册权限），调整卡片样式
- `ed39ed1` 先准备好飞书机器人菜单点击的脚手架，开始整合Notion数据库的逻辑

---

## 📊 **项目统计**

- **总提交数**: 40+ (2024年至今)
- **开发周期**: 2025年2月 - 至今
- **主要语言**: Python
- **架构模式**: 四层架构 (Adapters -> Business -> Application -> Services)

---

## 🔮 **未来规划**

### **即将发布**
- **v2.2.0**: 配置化关联实施版
- **v2.3.0**: 快速插拔验证版

### **长期规划**
- **LLM驱动路由**: 智能功能调用和参数识别
- **多平台支持**: MCP标准集成
- **功能扩展**: 文档处理、外卖决策、天气集成等

---

*最后更新: 2025-06-22*
*维护者: Izumi.屈源*