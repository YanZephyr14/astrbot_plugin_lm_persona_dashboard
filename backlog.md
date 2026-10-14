# 任务拆解与开发进度追踪 (backlog.md)

## 待办列表

- [x] **Phase 1: 规范与基础元数据**
  - [x] 创建插件目录 `data/plugins/astrbot_plugin_lm_persona_dashboard`
  - [x] 编写 `objective.md`
  - [x] 编写 `metadata.yaml` 与 `requirements.txt`
  - [x] 编写 `_conf_schema.json`（支持自定义数据库/数据目录路径）
  - [x] 编写国际化文案 `.astrbot-plugin/i18n/zh-CN.json` 与 `en-US.json`
  - [x] 编写 `backlog.md` 与 `test_plan.md`

- [x] **Phase 2: 存储与数据服务层 (store.py)**
  - [x] 智能路径探测器：优先级探测配置路径、当前运行时 plugin_data 路径、桌面启动器实例数据目录
  - [x] SQLite 异步连接与健康状态检查器
  - [x] 人格聚合器：整合系统 Persona 与 SQLite 实际存储的所有 persona_id（含通用/未归属）
  - [x] 人格维度统计器：统计每个人格的总记忆、活跃数、归档数、类型分布、原子记忆数
  - [x] 多维度分页检索器：支持按 persona_id、关键词、类型、状态、重要性、会话排序过滤
  - [x] 记忆详情查询：联合查询父记忆、关联 memory_atoms 及会话上下文
  - [x] 记忆编辑与人格转移：支持单条与批量修改 persona_id、内容、重要性、状态
  - [x] 记忆导出器：按选定人格导出为标准 JSON / CSV 格式

- [x] **Phase 3: 插件入口与 Web API (main.py)**
  - [x] 继承 `Star` 类实现生命周期管理
  - [x] 注册 RESTful Web API：
    - `GET /status`
    - `POST /set_active_db`
    - `GET /personas`
    - `GET /memories`
    - `GET /memory/<memory_id>`
    - `POST /memory/update`
    - `POST /memory/batch_persona`
    - `POST /memory/delete`
    - `GET /export`

- [x] **Phase 4: 前端可视化控制台 (views/ & pages/)**
  - [x] 现代 Glassmorphism 样式与主题自适应 (`style.css`)
  - [x] 前端应用入口与 Bridge 兼容适配 (`app.js`)
  - [x] 人格侧栏分类导航（搜索过滤、统计徽章、一键切换）
  - [x] 人格统计指示板与类型分布图表
  - [x] 记忆卡片流（实体标签、重要性展示、折叠原子记忆与上下文）
  - [x] 记忆编辑与人格转移模态框
  - [x] 批量操作工具条（批量转移人格、批量删除）
  - [x] 导出与数据库切换设置弹窗
  - [x] 双目录同步：保持 `views/dashboard/` 与 `pages/dashboard/` 完全一致

- [x] **Phase 5: 测试验证与交付**
  - [x] 编写数据层与 API 单元测试套件
  - [x] 使用真实数据库测试验证（赵依依、Zaoyyi、小鲸鱼等不同人格分类）
  - [x] 代码质量检查（ruff check & ruff format）
  - [x] Git 仓库初始化与 GitHub 远程同步 (`gh repo create`)
  - [x] 更新根目录 `DEVLOG.md`
