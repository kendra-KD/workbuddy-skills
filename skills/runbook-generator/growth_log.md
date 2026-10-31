# Growth Log — runbook-generator

> 进化日志。每次制作/迭代由第 ⑦ 步追加一条结构化记录。超过 50 条仅保留最近 30 条。

---

## #001 · 2026-10-31 · 首次创建（v1.0）

### 触发场景
用户（运维工程师）启动第三个 Skill，定位为运维工具链产品矩阵的「解决问题」环节。前两个 Skill：ssl-cert-monitor（发现问题）、issue-report-formatter（上报问题），第三个需要解决「故障发生时怎么排查」的痛点。选定方向：runbook 生成器——输入故障特征匹配预置实战 runbook。

### 方案选择
- **能力边界**：故障特征匹配预置 runbook + 结构化输出排查步骤+验证+回退+根因假设树。纯规则引擎，不调 AI API。
- **输入方式**：关键词匹配（`502`）+ 自然语言匹配（`echo "生产 502 了" | ...`）+ 列表/详情查看
- **内置 runbook**：10 个（502/503/504/timeout/connection-refused/cert-expiry/pod-crashloopbackoff/minio-s3-500/disk-full/oom-killed）
- **输出格式**：Markdown（人类阅读，可直接复制）+ JSON（程序化消费）
- **技术栈**：Python 标准库（argparse + json + 正则），零第三方依赖
- **作用域**：项目级（副业产品，可分发）
- **Fork/从零**：从零设计（SkillHub 检索最高契合度 50% troubleshoot-expert，<70%；现有 runbook 工具偏通用 SRE 模板，无中文运维场景适配，无实战 runbook 库）

### 最终效果
- 6 个文件：SKILL.md + runbook_lib.py（10 个 runbook 数据库）+ runbook_matcher.py（匹配引擎）+ runbook_catalog.md + custom_runbook_guide.md + runbook_template.md + insights.md + growth_log.md
- 10 个内置 runbook 覆盖运维高频故障，每个含根因假设树+排查步骤+验证+回退

### 关键决策
1. **纯规则引擎不调 AI API**（Rule 4）：跟 issue-report-formatter 的 assist 模式互补——assist 给 AI 提示词，runbook 给经过验证的步骤。零成本零延迟，离线可用。
2. **未匹配输出通用框架不臆造**（Rule 5）：安全兜底，不用 AI 编步骤。
3. **根因假设树按概率排序**（Rule 2）：强制用户逐个验证，避免撒网式乱试。
4. **每个 runbook 必含回退方案**（Rule 1）：安全红线，有副作用的操作必须可回退。
5. **命令可直接复制**（Rule 3）：占位符用尖括号标注，运维在压力下不想拼命令。
6. **实战 runbook 护城河**：内置的 minio-s3-500 runbook 含 vhost vs path-style 根因和 minio-nginx 统一入口方案，来自真实运维经验。

### 踩坑记录
| # | 问题 | 根因 | 修复 | 耗时 |
|---|------|------|------|------|
| 1 | SkillHub publish dry-run 报 "缺少 slug" | 新版 CLI（2026.8.5）要求 SKILL.md frontmatter 显式含 slug 字段 | 补 slug: runbook-generator | 低 |
| 2 | dry-run 报 "version 不是合法 SemVer" | version 填 "1.1" 不是三段式 | 改为 1.1.0 | 低 |
| 3 | dry-run 报 "缺少 displayName" | 字段名是驼峰 displayName 不是 display_name | 改为 displayName | 低 |

### 可复用经验（提炼给后续 Skill）
1. **SkillHub 发布 frontmatter 必备字段**：name + slug + displayName + version（SemVer 三段式）+ description + agent_created。前两个 Skill 的 slug 可以跟 name 一样，displayName 用中文友好名。
2. **产品矩阵第三环的设计思路**：不要跟第二环功能重叠，issue-report-formatter 的 assist 模式是「给 AI 提示词」，runbook-generator 是「给经过验证的步骤」，两者互补不冲突。
3. **实战经验是护城河**：通用 runbook 工具（如 Claude Code 的 runbook-generator）只给模板，我们的内置 runbook 含真实运维经验（如 MinIO vhost 问题），这是差异化竞争力。

### 待观察（暂不升级为规则）
- 10 个内置 runbook 的关键词匹配准确率未做大批量验证——当前依赖关键词列表，对自然语言描述的匹配可能不够精准。
- 自定义 runbook 接入方式目前只能改代码（runbook_lib.py），后续考虑支持 JSON 外部加载。
