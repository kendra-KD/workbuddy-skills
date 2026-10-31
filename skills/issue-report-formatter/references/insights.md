# Insights — issue-report-formatter 长期规则库

> 由第 ⑦ 步从 growth_log 提炼的高影响、可改变默认行为的经验。
> 生效中的规则是后续迭代/新建 Skill 时的默认行为，不需重新设计。

---

## 生效中的规则

### Rule 1 · 多字段抽取：先剥离会"污染"其他字段的字段

**规则**：当从同一段自然语言中抽取多个字段时，如果 A 字段的匹配范围会覆盖 B 字段的内容（如 error 抽取把"已试过..."吸入），**先抽取 A 字段并从原文剥离，再从剩余文本抽取 B 字段**。

**原因**：
- 试图用复杂 lookahead 约束边界容易出错（见 Rule 2）
- "先剥离再抽取"是架构级解决方案，比正则级修补更可靠
- 每个字段在"干净"的文本上抽取，准确率更高

**操作**：
```python
def extract_from_text(text):
    tried = extract_tried(text)  # 先抽取
    text_without_tried = re.sub(TRIED_PATTERN, '', text)  # 剥离
    return {
        "error": extract_error(text_without_tried),  # 从剩余文本抽取
        "tried": tried,
        ...
    }
```

**适用场景**：任何从自然语言抽取多个字段且字段间有内容重叠风险的 Skill。

---

### Rule 2 · 正则 lookahead 里不要嵌套字符类

**规则**：在正则的 lookahead `(?=...)` 内部，**不要嵌套字符类 `[:：]`**，否则容易导致正则引擎认为外层括号未闭合（`missing ), unterminated subpattern`）。

**原因**：
- Python re 模块对 lookahead 内字符类的解析有边界情况
- 出错信息（unterminated subpattern）不直观，难以定位

**替代方案**：
- 改用"先剥离再抽取"架构（见 Rule 1）
- 或用非字符类的方式表达，如 `(?::|：)` 代替 `[:：]`

**适用场景**：任何使用 lookahead 且内部需要匹配标点的正则。

---

### Rule 3 · 变现引导只加在人类阅读的输出，不加在结构化数据

**规则**：Skill 同时输出 Markdown（人类阅读）和 JSON（程序化消费）时，**变现引导/营销内容只加在 Markdown 末尾，JSON 保持干净**。

**原因**：
- JSON 可能被其他程序消费（批量统计/知识库沉淀），混入营销内容会污染数据
- Markdown 是人看的，变现引导放在末尾不影响阅读体验
- 双输出场景下，数据纯净性和变现触达可以兼得

**操作**：变现引导在 `generate_markdown_report()` 里追加，`generate_json()` 不含任何引导内容。

**适用场景**：任何同时输出人类可读格式和结构化数据的 Skill。

---

### Rule 4 · 核心能力独立成脚本，可独立运行也可被调用

**规则**：Skill 的核心能力（如紧急度分级、数据校验、格式转换）**独立成可单独运行的脚本**，既可被主脚本 import 调用，也可用 `python xxx.py` 独立使用。

**原因**：
- 复用性好：用户可能只需要分级不需要完整报告
- 可测试性好：独立脚本更容易做单元测试
- 职责清晰：每个脚本做一件事

**操作**：classify_severity.py 独立可用（`echo "..." | python classify_severity.py`），同时 format_report.py 内部也调用其 classify 函数。

**适用场景**：任何有多个独立能力的 Skill。

---

### Rule 5 · 跨 Skill 产品矩阵设计

**规则**：做第二个 Skill 时，**主动思考是否能跟已有 Skill 形成产品矩阵**（如"发现问题"→"上报问题"→"解决问题"），而不是孤立选品。

**原因**：
- 矩阵产品有协同效应：用户装了一个会想装另一个
- 降低获客成本：已有用户是天然转化池
- 形成"运维工具链"品牌认知，提升整体专业感

**操作**：ssl-cert-monitor（发现问题）→ issue-report-formatter（上报问题），第三个 Skill 可以考虑"解决问题"方向（如 runbook 生成器/故障排查助手）。

**适用场景**：任何做第三个及以后 Skill 的选品决策。

---

### Rule 6 · AI 协作产物用"提示词+清单+假设树"三件套

**规则**：当 Skill 需要让用户"整理信息同步给 AI 辅助解决"时，**不要只生成一段提示词**，而是输出三件套：① 结构化提示词（含角色/任务/约束） ② 排查 checklist（每项含检查什么+怎么查+命令） ③ 诊断假设树（可能原因+验证方法+预期结果）。

**原因**：
- 只给提示词，AI 容易跳步或直接给"重启试试"这种无根因方案
- checklist 让用户自己也能照着查，不依赖 AI
- 假设树给 AI 一个"思考框架"，强制它按顺序逐个验证，验证完一个再下一个
- 三件套覆盖了"AI 辅助""人工自查""思考框架"三个场景

**操作**：assist 模式输出三份产物，提示词里内嵌 checklist 和假设树，用户复制粘贴一次即可。

**适用场景**：任何需要"整理信息同步给 AI"的 Skill。

---

### Rule 7 · assist 模式只生成提示词，不直接调 AI API

**规则**：Skill 的 AI 协作模式（assist）**只生成提示词让用户复制粘贴给任意 AI**，不在 Skill 内部直接调 AI API。

**原因**：
- 密钥管理复杂度高（API key 存哪里、怎么轮换、怎么避免泄露）
- 有成本（调 AI API 要花钱，免费额度有限）
- 锁定单一 AI（调 OpenAI 就不能换 Claude，用户没有选择权）
- 用户可能已有 ChatGPT Plus / Claude Pro，复制粘贴零成本

**操作**：generate_ai_prompt.py 只输出文本，不 import openai/anthropic 等 SDK。

**适用场景**：任何 Skill 的 AI 协作模式设计。

---

### Rule 8 · Python 字符串内避免中文引号嵌套

**规则**：Python 字符串（尤其是双引号字符串）内部**不要直接嵌入中文引号""**，否则会导致 `SyntaxError: invalid syntax`（Python 把中文引号当成字符串结束符）。

**原因**：
- Python 字符串用 `"` 或 `'` 包裹，中文引号 `""` 在某些编码下会被解析器误判
- 报错信息 `Is this intended to be part of the string?` 不直观

**替代方案**：用中文书名号 `『』` 或 `「」` 代替，或用转义。

**适用场景**：任何在 Python 字符串里需要表达"引用"语义的 Skill。
