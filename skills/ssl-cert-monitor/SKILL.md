---
name: ssl-cert-monitor
slug: ssl-cert-monitor
displayName: SSL证书到期巡检
version: 1.1.1
description: "SSL/TLS 证书到期批量巡检工具。检查 HTTPS 域名证书剩余有效期，按紧急度（≤7天紧急、≤30天警告、已过期）排序生成 Markdown 报告与 JSON 数据，附 Let's Encrypt/阿里云/腾讯云/华为云续签指引。触发短语：'检查证书到期'、'SSL 巡检'、'证书快过期'、'批量检查证书'、'cert expiry monitor'、'check cert expiry'、'ssl certificate monitor'。面向运维、SRE、技术支持、私有化交付。仅检查与报告，不自动续签。纯 Python 标准库，零依赖。"
agent_created: true
---

# SSL Cert Monitor · SSL 证书到期巡检

## Overview

批量检查 HTTPS 域名的 SSL/TLS 证书剩余有效期，按紧急程度排序输出 Markdown 表格报告与 JSON 结构化数据，并附带各平台证书续签操作指引。面向任何 HTTPS 运维场景，不绑定特定云厂商、公司或域名。仅做检查与报告，不自动执行续签。

**解决什么痛点**：证书过期是运维最容易踩的坑之一——没有定期巡检机制时，证书静默过期会导致线上 HTTPS 服务整站不可用，浏览器报 NET::ERR_CERT_DATE_INVALID，CDN 回源失败，甚至触发客户投诉。手写脚本检查又容易漏 SAN 域名、漏已过期证书、漏泛域名匹配，且 Windows 环境 Python 的 CA 库可能缺失根证书导致验证失败。这个 Skill 把证书巡检标准化：一份 CSV 域名清单进去，一份按紧急度排序的巡检报告出来，任何环境都能跑。

**核心能力**：
1. **批量检查**：一次检查几十上百个域名，串行处理 + 单域名 10 秒超时，单个失败不中断整体流程
2. **紧急度分级**：🔴紧急（≤7天）/ 🟡警告（≤30天）/ 🟢正常（>30天）/ ⚫已过期，按紧急度排序输出
3. **双输出格式**：Markdown 表格报告（人类阅读，可直接复制到企业微信/钉钉）+ JSON 结构化数据（程序化消费，便于接入告警/知识库）
4. **全平台续签指引**：附 Let's Encrypt / 阿里云 / 腾讯云 / 华为云 四个平台的续签操作文档要点，不自动执行
5. **零环境依赖**：纯 Python 标准库（ssl + socket），不依赖第三方包，不依赖环境 CA 证书库，Windows/Linux/Mac 都能跑

**适用场景**：
- 定期运维巡检，防止证书静默过期导致线上事故
- 批量盘点手头所有域名的证书到期情况，按紧急度排序出清单
- 接手新环境或交接时，快速摸清证书现状
- 证书续签前的现状评估，决定哪些先续、哪些可以后补
- 私有化交付前的证书健康度检查，作为交付物的一部分

**不适用场景**：
- 自动续签证书（本 Skill 只做检查与报告，续签由人工按指引执行）
- 自动部署证书到 K8s/CDN/Nginx（属于其他 Skill 范畴）
- 检查非 HTTPS 服务的证书（如 SMTP/IMAP STARTTLS，当前只支持 HTTPS 443 及自定义端口直连）
- 实时证书监控（本 Skill 是一次性巡检工具，不是持续监控告警系统）

---

## 工作流程

### 触发方式

用户说以下任一短语时触发：
- 中文：检查证书到期 / SSL 巡检 / 证书快过期 / 批量检查证书 / 证书到期检查
- 英文：cert expiry monitor / check cert expiry / ssl certificate monitor / tls certificate check

### 对话使用示例（用户怎么用）

**你不需要去终端敲命令。** 装了这个 Skill 后，直接在对话里用自然语言描述需求，WorkBuddy 会自动识别触发短语并加载本 Skill。

#### 场景 1 · 定期巡检（最常用）

> **你说**：帮我做一下证书巡检 / 检查证书到期情况

如果你有 CSV 域名清单（放在 `assets/domains_template.csv`），批量检查所有域名；如果没有，你直接在对话里列出域名（如 `example.com`、`blog.example.com:8443`），Skill 解析后检查，输出按紧急度排序的报告。

#### 场景 2 · 临时查单个域名

> **你说**：检查 example.com 的证书还有多久过期

单个域名检查，立即出结果（紧急/警告/正常/已过期）。

#### 场景 3 · 接手新环境盘点

> **你说**：盘点一下这个环境的证书情况 / 证书健康检查

批量扫所有域名，按紧急度排序出清单，接手时一目了然。

#### 场景 4 · 证书快过期了怎么办

> **你说**：证书快过期了怎么处理

检查到紧急/警告级别后，Skill 会根据证书颁发者匹配对应平台的续签指引（Let's Encrypt / 阿里云 / 腾讯云 / 华为云），给出操作要点，**不自动执行续签**。

### Step 1 · 获取域名清单

从以下两种输入之一获取待检查的域名清单：

- **CSV 文件**：读取 `assets/domains_template.csv` 格式的清单（字段：`domain,port`，默认端口 443）。适合批量盘点、可版本化复用。
- **对话临时输入**：用户在对话中直接列出域名（如 `example.com`、`blog.example.com:8443`），解析后传给检查脚本。适合临时排查。

若用户未指定端口，默认使用 443。

### Step 2 · 执行证书检查

运行 `scripts/check_certs.py`，对清单中每个域名执行：

1. 用 Python 标准库 `ssl` + `socket` 建立 TLS 连接（10 秒超时）
2. 用 `get_unverified_chain()` 拿 DER 证书 + `_ssl._test_decode_cert()` 解析（不依赖环境 CA 库）
3. 提取 `notAfter`（到期时间）、`issuer`（颁发者）、`subject`（主体）、`SAN`（备用域名）
4. 计算剩余天数 = 到期时间 - 当前时间
5. 按紧急程度分级：
   - 🔴 **紧急**：剩余 ≤ 7 天
   - 🟡 **警告**：剩余 ≤ 30 天
   - 🟢 **正常**：剩余 > 30 天
   - ⚫ **已过期**：剩余 < 0
6. 输出 JSON 结构化数据到 `scripts/check_result.json`

**容错处理**：单个域名检查失败（连接超时、DNS 解析失败、证书无效）时，记录错误原因并继续检查下一个，不中断整体流程。

### Step 3 · 生成报告

运行 `scripts/generate_report.py`，读取 `check_result.json`，生成双输出：

- **Markdown 表格报告**：按紧急程度排序（已过期 → 紧急 → 警告 → 正常），包含域名、端口、颁发者、到期日、剩余天数、状态标记、错误信息（若有）。输出到 `scripts/cert_report.md`。
- **JSON 结构化数据**：保留 `check_result.json` 供后续程序消费或接入告警系统。

### Step 4 · 呈现结果与续签指引

将 Markdown 报告呈现给用户，并针对紧急/警告/已过期级别的证书：

1. 询问用户是否需要查看对应平台的续签操作指引
2. 若需要，根据证书颁发者匹配 `references/renewal_guide.md` 中的对应章节（Let's Encrypt / 阿里云 / 腾讯云 / 华为云）
3. 给出操作指引要点，**不自动执行续签**

### Step 5 · 后续建议

根据检查结果给出建议：
- 已过期证书：立即续签，已导致服务不可用
- 紧急证书：立即续签，附对应平台指引
- 警告证书：安排本周内续签
- 正常证书：下次定期巡检时复查
- 提醒用户可设置定期巡检节奏（建议每周或每两周一次）

### 调用示例

```bash
# 方式一：CSV 清单批量检查（推荐，可版本化复用）
python scripts/check_certs.py --csv assets/domains_template.csv --output check_result.json
python scripts/generate_report.py --input check_result.json --output cert_report.md
# 报告输出到 cert_report.md

# 方式二：对话临时输入（适合临时排查单个/几个域名）
# 直接在对话里说"检查 example.com、blog.example.com:8443 的证书到期情况"

# 方式三：只看 JSON 结构化数据（便于接入告警系统）
cat check_result.json
```

**Markdown 报告示例**：
```markdown
| 域名 | 端口 | 颁发者 | 到期日 | 剩余天数 | 状态 |
|------|------|--------|--------|---------|------|
| expiring.example.com | 443 | Let's Encrypt | 2026-11-05 | 5 | 🔴 紧急 |
| normal.example.com | 443 | DigiCert | 2027-03-20 | 143 | 🟢 正常 |
```

---

## 引用文件

| 文件 | 用途 |
|------|------|
| `scripts/check_certs.py` | 核心检查脚本，读取域名清单，查询证书并输出 JSON |
| `scripts/generate_report.py` | 报告生成脚本，JSON 转 Markdown 表格并按紧急度排序 |
| `references/cert_knowledge.md` | 证书基础知识参考：类型/证书链/SAN/泛域名证书/常见问题排查 |
| `references/renewal_guide.md` | 各平台证书续签操作指引：Let's Encrypt / 阿里云 / 腾讯云 / 华为云 |
| `assets/domains_template.csv` | 域名清单模板（字段：domain,port） |

---

## 约束与边界

### 安全红线
1. **只做检查与报告，不自动执行续签**：续签涉及账号操作和密钥管理，必须人工执行
2. **只用 Python 标准库**（`ssl` + `socket`），不依赖第三方包，不依赖环境 CA 证书库
3. **不硬编码任何域名、密钥、账号信息**：域名清单由用户提供，只在本地处理
4. **不绑定特定云厂商或公司**：任何 HTTPS 域名都能检查
5. **域名清单只在本地处理**，不上传任何外部服务，不存储到云端

### 适用边界
- 适合：定期运维巡检、批量证书盘点、交接环境摸底、续签前现状评估
- 不适合：自动续签、自动部署证书到 K8s/CDN/Nginx、非 HTTPS 证书检查、实时持续监控
