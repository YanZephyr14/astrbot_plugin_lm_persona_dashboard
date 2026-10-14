# LivingMemory 人格记忆看板 (LM Persona Dashboard)

> 🧠 **专为 LivingMemory 打造的伴侣辅助插件**：提供按角色人格设定（Persona）深度分类、检索、洞察与管理长期记忆的增强控制台。

[![AstrBot Plugin](https://img.shields.io/badge/AstrBot-Plugin-blue.svg)](https://github.com/Soulter/AstrBot)
[![Version](https://img.shields.io/badge/version-v1.0.0-green.svg)](https://github.com/YanZephyr14/astrbot_plugin_lm_persona_dashboard)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 为什么需要这个辅助插件？

原长期记忆插件 [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) 拥有完整的记忆提取生命周期和图检索机制，但其自带的 Dashboard 目前只支持全部平铺展示或单一会话过滤，**无法按角色人格设定（Persona）分类查看记忆**。

当用户在 AstrBot 中设定了多个不同性格的角色（如：助手、小鲸鱼、赵依依、猫娘、英语老师等）时，所有角色的记忆全部混杂在一起，浏览与维护极不方便。

**本插件在【完全不修改原 LivingMemory 插件】的前提下应运而生：**
- 🛡️ **绝对零侵入**：纯外挂/伴侣模式，只读写底层标准 SQLite 数据，不修改原插件任何源码或文件。
- 🔄 **随装随卸**：未来原作者如果原生支持了人格分类查看，你可以随时无缝停用或卸载本辅助插件，对记忆数据无任何副作用。

---

## 🚀 核心功能亮点

### 1. 👥 人格智能聚合与侧栏快速切换
- 自动整合当前 AstrBot 配置的角色人格与数据库中所有历史 `persona_id`。
- 左侧分类导航清晰展示每个角色人格的记忆总数、活跃条数、原子记忆数。
- 支持“所有人格总览”、“具体角色人格”及“未指定人格设定 (Unassigned)”三维归类。

### 2. 📊 角色记忆深度画像与分布洞察
- 选定某个人格后，自动生成该角色的记忆画像：
  - 记忆类型彩色彩虹比例条（事实 FACT、偏好 PREFERENCE、日常 GENERAL、事件 EVENT 等）。
  - 总记忆、活跃记忆、原子记忆计数与平均重要性评分。

### 3. 🔍 专属高阶过滤与关键词检索
- 支持在当前所选人格范围内，根据记忆关键词、ID、话题标签（Topics）进行防抖实时搜索。
- 支持按记忆类型、状态（活跃/归档）、重要性星级、排序规则（最新、最早、重要性优先）精准筛选。

### 4. 🔬 原子记忆 (Memory Atoms) 与会话上下文透视
- 单条记忆卡片可一键折叠展开其拆解出的 **Memory Atoms（原子命题）**，细致查看每个命题的置信度、TTL、衰减状态。
- 若存在来源会话记录，支持展开追溯当时触发该记忆形成的上下文对话片段。

### 5. 🔀 记忆跨角色转移与编辑维护
- **跨人格转移**：遇到多角色互动串台或归属错位的记忆，可在编辑弹窗中一键将其修改为目标角色人格，或通过多选框**批量转移**给指定角色！
- 修改记忆内容、调整重要性权重滑块（0-10 分）、软删除/归档。

### 6. 💾 角色记忆独立导出
- 支持一键将当前选定角色人格的全部记忆导出为标准 **JSON** 或 **CSV** 表格，方便角色记忆单独备份与跨平台迁移。

### 7. 🔌 智能多实例探测与数据源即时切换
- 自动探测宿主 AstrBot 环境或桌面启动器实例（`~/.astrbot_launcher/instances/`）下的数据库。
- 弹窗内直观列出所有候选数据库，支持一键切换或手动输入自定义路径。

---

## 🖥️ WebUI 访问方式

1. 打开 AstrBot 管理控制台 (WebUI)。
2. 进入 **插件** 列表页面。
3. 找到 **LM 人格记忆看板**（`astrbot_plugin_lm_persona_dashboard`），点击进入即可打开专属全功能看板！
4. 支持暗黑/明亮主题自适应。

---

## 💬 交互指令

- `/lm_persona`：在聊天窗口中快速查看当前各角色人格的记忆统计概览与数据库连接状态。

---

## ⚙️ 配置项说明 (`_conf_schema.json`)

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `custom_data_dir` | string | `""` | 自定义 LivingMemory 数据目录路径（可选）。留空时插件将自动探测当前 AstrBot 或桌面启动器实例下的数据库。 |
| `page_size` | number | `15` | 看板每页展示条数（5 - 100）。 |
| `enable_editing` | boolean | `true` | 是否允许在看板中编辑记忆与修改人格归属。 |
| `enable_deletion` | boolean | `true` | 是否允许在看板中归档或删除记忆。 |

---

## 📄 开源许可

[MIT License](LICENSE)
