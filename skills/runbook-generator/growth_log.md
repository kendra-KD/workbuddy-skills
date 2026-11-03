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
- ~~10 个内置 runbook 的关键词匹配准确率未做大批量验证~~ → v1.1 已优化匹配算法（加 title 匹配 + 三级评分），自然语言召回率提升。
- 自定义 runbook 接入方式目前只能改代码（runbook_lib.py），后续考虑支持 JSON 外部加载。

---

## #002 · 2026-11-03 · v1.1 升级（数据驱动扩 runbook + 体验优化）

### 触发场景
SkillHub 后台数据显示 ops-fault-runbook 是四件套下载量最高的（19 次），用户决定不急着做第 5 个新 skill，而是把下载最多的 runbook 做深度迭代：扩内置模板 + 体验优化，让已有用户觉得更好用、带来口碑传播。**这是从"凭感觉选题"转向"数据驱动选题"的第一次实践。**

### 方案选择
- **扩 5 个 runbook**（10→15）：DNS 解析失败 / 数据库连接失败 / K8s Pod Pending / Docker 容器无法启动 / Nginx 配置语法错误。选取标准：① 行业高频故障 ② 用户有实战经验 ③ 现有 10 个未覆盖。
- **体验优化 3 项**：
  1. 四件套交叉导流（SKILL.md description 加"运维全生命周期四件套之一"，产品矩阵从三件套改四件套）
  2. 未匹配推荐最接近的（新增 `match_runbooks_topn` 函数，未匹配时输出 top-3 推荐而非只给通用框架）
  3. 匹配算法升级（`_score_runbook` 三级评分：精确匹配+50 / 包含关键词+len*2 / 被包含+len；新增 title 弱匹配提升自然语言召回率）
- **版本**：1.0.0 → 1.1.0

### 最终效果
- runbook_lib.py：10 个 → 15 个 runbook，新增 `match_runbooks_topn` + `_score_runbook` 函数
- runbook_matcher.py：import 加 topn，`generate_no_match_markdown` 加推荐块
- SKILL.md：version→1.1.0，description 加交叉导流+15 个故障清单，runbook 清单表补 5 行，产品矩阵改四件套
- runbook_catalog.md：补 5 个新 runbook 的目录详解
- 实测 60/60 全通过（新增匹配 13 + detail 15 + topn 3 + 未匹配 4 + 原有 10 + JSON 5 + 安全 2 + stdin 1 + list 7）

### 关键决策
1. **数据驱动扩 runbook 而非做新 skill**：下载量证明 ops-fault-runbook 需求最强，扩它的模板比从 0 攒新 skill 投入产出比高。
2. **匹配算法三级评分**：解决了"短查询被长关键词误匹配"问题（`connection refused` 不再跑到 db-connection-failure）。
3. **title 弱匹配**：`gateway error 500` 这类自然语言能通过 title 里的 "gateway" 命中 http-502，提升召回率。
4. **未匹配推荐 top-3**：从"只给通用框架"升级为"通用框架 + 最接近的 3 个 runbook 预览"，降低用户重新输入的成本。

### 踩坑记录
| # | 问题 | 根因 | 修复 | 耗时 |
|---|------|------|------|------|
| 1 | `mysql connection refused` 匹配到 connection-refused 而非 db-connection-failure | db 关键词都是中文或顺序敏感，英文组合词缺失 | 加 `mysql connection`/`postgres connection` 英文关键词 + 匹配算法三级评分让短精确词优先 | 中 |
| 2 | `connection refused` 加新关键词后跑到 db-connection-failure | `connection refused mysql` 关键词被 `in query` 误加分 | 三级评分：`query in kw` 从 `len*2` 降为 `len`，避免长关键词的包含匹配压过短精确匹配 | 中 |
| 3 | `gateway error 500` 完全不匹配 | 只有关键词参与匹配，title 不参与 | `_score_runbook` 加 title 弱匹配（单词≥3 字符命中加 len 分） | 低 |

### 可复用经验（提炼给后续 Skill）
1. **匹配类 Skill 的评分算法要分级**：精确匹配（==）最高、查询包含关键词（kw in query）次之、关键词包含查询（query in kw）最低。不分级会导致泛化词误匹配。
2. **title 参与匹配提升自然语言召回率**：用户不会精确输入关键词，会输入描述性语言（"gateway error 500"），title 弱匹配是低成本提升召回的方法。
3. **数据驱动迭代的优先级**：下载最多的 skill 优先做深度迭代（扩模板/优化体验），而不是做新 skill。已有用户的口碑传播比从 0 攒新用户效率高。

### 待观察
- 15 个 runbook 的关键词覆盖是否够：等 v1.1 发布后看是否有人反馈"输入 XX 匹配不到"。
- title 弱匹配是否会导致误匹配：`gateway` 可能同时命中 502/503/504 的 title，需观察是否需要进一步区分。
