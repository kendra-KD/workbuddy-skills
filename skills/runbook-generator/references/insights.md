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
