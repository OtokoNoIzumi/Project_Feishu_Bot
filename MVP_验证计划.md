# MVP验证计划

## 概述
这是一个可逐步验证的重构计划，每个阶段都有明确的可验证交付物。

## ⚠️ 重要：Conda虚拟环境规范

### 环境处理规范
1. **项目环境**：项目基于conda虚拟环境WorkSpace（python 3.11.9）
2. **路径处理**：所有配置服务必须正确处理项目根路径，不依赖系统默认路径
3. **环境变量**：.env文件位于项目根目录，包含开发/生产环境差异配置
4. **验证限制**：当前shell环境无法直接切换conda环境，验证时使用base环境进行测试

### 🚫 Conda环境切换限制
**已验证：在当前cursor shell环境中无法成功切换conda环境**
- conda命令可用，可以列出环境列表
- `conda activate WorkSpace` 执行但不生效（仍在base环境）
- **规范要求**：所有验证都在base环境进行，不尝试切换虚拟环境
- **项目架构**：配置服务设计必须适配这种限制

### 配置架构（三层优先级）
1. **环境变量(.env)** - 最高优先级，开发/生产环境差异
2. **认证配置文件** - 中等优先级，通过AUTH_CONFIG_FILE_PATH指定
3. **静态配置(config.json)** - 最低优先级，业务配置

### 测试规范
- 测试脚本不创建假的环境变量
- 使用真实项目的.env文件进行验证
- 明确区分测试环境和真实环境的配置值
- 核心功能验证通过即可，不追求100%测试覆盖

## 阶段1：缓存服务迁移和验证 ✅

### 已完成
- [x] 创建 `Module/Services/cache_service.py`（新位置，具体文件名）
- [x] 保持所有原有接口兼容
- [x] 新增 `get_status()` 和 `clear_expired()` 方法
- [x] 创建 `test_cache_service.py` 验证脚本
- [x] 创建 `api_demo.py` FastAPI演示

### 验证方式
```bash
# 1. 基础功能验证
python test_cache_service.py

# 2. API接口验证（需要先安装依赖）
pip install fastapi uvicorn
python api_demo.py
# 然后访问 http://localhost:8000/docs
```

### 预期结果
- ✅ 所有原有功能正常工作
- ✅ 新增状态查询功能可用
- ✅ FastAPI接口可以通过浏览器访问和测试

---

## 阶段2：配置服务迁移和验证 ✅ **已完成**

### 已完成
- [x] 创建 `Module/Services/config_service.py`
- [x] **重要修复**：正确支持conda虚拟环境项目架构
- [x] **三层配置架构**：环境变量 > 认证配置 > 静态配置
- [x] **路径处理**：与main_new.py保持一致的项目根路径逻辑
- [x] 创建 `test_config_service.py` 验证脚本（已修正）
- [x] 创建 `config_api_demo.py` FastAPI演示
- [x] **✅ 核心验证通过**：AUTH_CONFIG_FILE_PATH正确读取，认证配置文件正确加载

### 核心改进
1. **正确的项目路径处理**：模拟main_new.py的路径检测逻辑
2. **环境变量优先级**：AUTH_CONFIG_FILE_PATH从.env读取，不是config.json
3. **配置来源追踪**：提供get_config_source()方法
4. **安全配置**：敏感信息自动隐藏
5. **项目信息**：get_project_info()用于调试conda环境

### 验证结果 ✅
**关键验证已通过：**
- ✅ AUTH_CONFIG_FILE_PATH 正确从环境变量读取
- ✅ 认证配置文件存在: `C:\Users\A\\Project_QRRag\auth_config.json`
- ✅ 三层配置架构正确工作（7个环境变量 + 9个静态配置 + 3个认证配置）
- ✅ 配置优先级验证: `env_vars > auth_config > static_config`
- ✅ 与main_new.py使用模式完全兼容

**API接口验证：**
```bash
python config_api_demo.py
# 访问 http://localhost:8001/docs 测试API接口
```

---

## 阶段3：简单的应用控制器验证 📋

### 计划内容
- [ ] 创建简化的应用控制器
- [ ] 实现服务注册功能
- [ ] 创建统一的服务调用接口
- [ ] 验证多服务协同工作

### 验证颗粒度
1. **服务注册**：能否正确注册多个服务
2. **服务调用**：能否通过控制器调用服务
3. **错误处理**：异常是否正确传播
4. **性能测试**：内存和CPU消耗是否合理

---

## 阶段4：飞书适配器实现 📋

### 计划内容
- [ ] 创建 `Module/Adapters/feishu_adapter.py`
- [ ] 实现消息转换逻辑
- [ ] 保持与现有飞书代码的兼容
- [ ] 创建适配器验证脚本

### 验证颗粒度
1. **消息转换**：飞书消息能否正确转换为统一格式
2. **响应处理**：统一响应能否正确转换为飞书格式
3. **向后兼容**：现有的飞书功能是否仍然正常
4. **性能对比**：新旧方式的性能差异

---

## 阶段5：主入口重构 📋

### 计划内容
- [ ] 重构 `main_new.py` 使用新架构
- [ ] 实现平滑迁移（新旧代码可并存）
- [ ] 创建对比测试脚本
- [ ] 性能和稳定性验证

### 验证颗粒度
1. **功能完整性**：所有原有功能是否保持
2. **性能对比**：启动时间、内存使用、响应速度
3. **稳定性测试**：长时间运行是否稳定
4. **错误恢复**：异常情况下的恢复能力

---

## 进程管理和资源优化方案

### API服务器设计
```python
# 方案1：嵌入式API（推荐用于开发和轻量使用）
class EmbeddedAPIServer:
    def __init__(self, services):
        self.app = FastAPI()
        self.services = services
        self.setup_routes()

    def start_background(self):
        # 在后台线程启动API服务器
        pass

# 方案2：独立进程API（用于生产环境）
class StandaloneAPIServer:
    def start_separate_process(self):
        # 启动独立的API服务器进程
        pass
```

### 资源优化策略
1. **内存共享**：服务间共享配置和缓存对象
2. **懒加载**：API服务器只在需要时启动
3. **连接池**：数据库和外部API连接复用
4. **进程通信**：使用队列进行进程间通信

---

## 每阶段的验证标准

### 功能验证
- [ ] 所有测试脚本通过
- [ ] 新功能按预期工作
- [ ] 旧功能保持兼容

### 性能验证
- [ ] 启动时间不超过原有的120%
- [ ] 内存使用不超过原有的150%
- [ ] 响应时间不超过原有的110%

### 稳定性验证
- [ ] 连续运行24小时无崩溃
- [ ] 异常情况能正确恢复
- [ ] 日志记录完整且有用

---

## 当前状态

### ✅ 已完成
- 缓存服务迁移和验证脚本
- 配置服务迁移和验证脚本
- FastAPI接口演示（缓存和配置）
- 文件命名规范改进

### 🔄 进行中
- 等待阶段2的用户验证确认

### ⏳ 待办
- 应用控制器实现
- 飞书适配器创建
- 主入口重构

---

## 用户验证指南

### 验证阶段2
1. 运行 `python test_config_service.py`
2. 检查所有测试是否通过
3. 运行 `python config_api_demo.py`
4. 访问 http://localhost:8001/docs 测试API
5. 确认配置功能按预期工作

### 问题反馈
如果发现任何问题，请：
1. 记录具体的错误信息
2. 说明期望的行为
3. 提供复现步骤

### 继续条件
只有当前阶段完全验证通过后，才进入下一阶段的开发。

---

## 阶段2完成总结

### 新增功能
- `get_status()` - 获取配置服务状态
- `get_safe_config()` - 获取安全配置（隐藏敏感信息）
- `validate_config()` - 验证配置完整性
- `reload_all_configs()` - 重新加载所有配置

### API接口
- GET `/api/config/status` - 配置服务状态
- GET `/api/config/safe` - 安全配置
- GET `/api/config/validate` - 配置验证
- GET `/api/config/key/{key}` - 获取指定配置项
- POST `/api/config/update` - 更新配置项
- POST `/api/config/reload` - 重新加载配置
- GET `/api/config/keys` - 列出所有配置键