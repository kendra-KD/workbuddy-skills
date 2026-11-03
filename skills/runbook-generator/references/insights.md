# Insights — runbook-generator 长期规则库

> 由第 ⑦ 步从 growth_log 提炼的高影响、可改变默认行为的经验。
> 生效中的规则是后续迭代/新建 Skill 时的默认行为，不需重新设计。

---

## 生效中的规则

### Rule 1 · Runbook 必含回退方案（安全红线）

**规则**：每个 runbook 的每步有副作用的操作，**必须配回退方案**。runbook 末尾的 `rollback` 字段不能为空。

**原因**：
- 运维操作有风险，用户照着 runbook 执行可能改配置/删数据
- 没有回退方案，出问题后用户不知道怎么恢复
- 回退方案是安全底线，跟「不自动执行命令」一起构成安全边界

**操作**：写 step 时问自己「这步如果做错了怎么办」，把答案写进 rollback。

**适用场景**：任何 runbook 的编写。

---

### Rule 2 · 根因假设树按概率排序，强制逐个验证

**规则**：runbook 的 `root_causes` 数组**按概率从高到低排序**，并在输出时提示用户「按顺序逐个验证，验证完一个排除后再验证下一个」。

**原因**：
- 故障排查最忌讳「撒网式」乱试，效率低且可能引入新问题
- 按概率排序让用户先验证最可能的原因，快速定位
- 强制逐个验证避免跳步导致误判

**操作**：root_causes 每条标 probability（高/中/低），输出时用 🔴🟡🟢 标注。

**适用场景**：任何含根因假设的 runbook。

---

### Rule 3 · 命令必须可直接复制，占位符用尖括号

**规则**：runbook 中的 command **必须是可直接复制执行的完整命令**，需要用户替换的参数用 `<占位符>` 标注（如 `kubectl get pod -n <namespace>`）。

**原因**：
- 运维在故障压力下不想拼命令，给完整的直接复制
- 尖括号占位符一眼能看出需要替换什么
- 避免命令不完整导致执行报错，增加排查负担

**操作**：写 command 时把所有需要用户填的参数用 `<>` 包裹。

**适用场景**：任何 runbook 命令编写。

---

### Rule 4 · 产品矩阵第三环：解决问题 ≠ 调 AI API

**规则**：runbook-generator 作为产品矩阵的「解决问题」环节，**用纯规则引擎匹配预置 runbook，不调 AI API**（继承 issue-report-formatter 的 Rule 7）。

**原因**：
- 零成本零延迟：故障发生时不需要等 AI 响应
- 可靠性高：预置 runbook 经过实战验证，不会臆造步骤
- 离线可用：不依赖网络和 AI 服务可用性
- 与 issue-report-formatter 的 assist 模式形成互补：assist 模式生成提示词给 AI 辅助排查，runbook-generator 直接给经过验证的步骤

**操作**：runbook_matcher.py 纯规则匹配，不 import openai/anthropic 等 SDK。

**适用场景**：runbook-generator 的核心引擎设计。

---

### Rule 5 · 未匹配到 runbook 时输出通用框架，不臆造步骤

**规则**：当用户输入的关键词没有匹配到任何预置 runbook 时，**输出通用排查框架 + 可用 runbook 列表**，而不是用 AI 臆造排查步骤。

**原因**：
- 臆造的步骤没经过实战验证，可能误导用户
- 通用框架（收集信息→分层排查→上报）是安全的兜底
- 列出可用 runbook 让用户检查是否有接近的

**操作**：match_runbook 返回 None 时，调用 generate_no_match_markdown 输出通用框架。

**适用场景**：runbook 匹配失败时的降级处理。

---

### Rule 6 · 匹配评分算法要分级（从 v1.1 提炼）

**规则**：关键词匹配类 Skill 的评分算法必须分三级：
- **精确匹配**（关键词 == 查询）：+50（最高，用户说的就是这个词）
- **查询包含关键词**（关键词 in 查询）：+len(kw)*2（关键词越长越具体）
- **关键词包含查询**（查询 in 关键词）：+len(query)（弱匹配，可能是泛化词被长关键词包含）

**原因**：不分级的旧算法（`kw in query` 和 `query in kw` 都加分）会导致"短查询被长关键词误匹配"。例如 `connection refused` 查询会被 `connection refused mysql` 这个长关键词的 `query in kw` 规则加分，导致 db-connection-failure 得分超过 connection-refused。

**操作**：`_score_runbook` 函数实现三级评分，精确匹配权重远高于包含匹配。

**适用场景**：任何基于关键词匹配的 Skill。

---

### Rule 7 · title 参与弱匹配提升自然语言召回率（从 v1.1 提炼）

**规则**：runbook/模板类 Skill 的匹配引擎，除了关键词匹配外，应让 title 也参与弱匹配——查询中的单词（≥3 字符）如果出现在 title 里，加 len(word) 的弱分。

**原因**：用户不会精确输入关键词，会输入描述性语言（如 "gateway error 500"）。只靠关键词匹配会漏掉这类查询。title 含故障类型名称（"502 Bad Gateway"），单词命中 title 能低成本提升召回率。

**操作**：`_score_runbook` 函数末尾加 title 匹配块，权重低于关键词（len(word) vs len(kw)*2）。

**适用场景**：任何含 title 字段的模板匹配类 Skill。

---

### Rule 8 · 未匹配时推荐最接近的 top-N（从 v1.1 提炼）

**规则**：匹配类 Skill 在未匹配到精确结果时，除了输出通用框架外，应输出"最接近的 N 个"推荐（按匹配分数降序取 top-3），每个推荐含 title + 关键词 + 概述摘要 + 查看命令。

**原因**：用户输入可能差一点就匹配上了（如 "证书" 匹配不到 "证书过期"）。只给通用框架让用户从头来，推荐最接近的能降低用户重新输入的成本。

**操作**：新增 `match_runbooks_topn(query, n=3)` 函数，`generate_no_match_markdown` 在通用框架前加推荐块。

**适用场景**：任何匹配失败有降级处理的 Skill。
