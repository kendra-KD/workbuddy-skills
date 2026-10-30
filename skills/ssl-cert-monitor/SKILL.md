---
name: ssl-cert-monitor
description: "SSL/TLS 证书到期巡检与提醒工具。批量检查 HTTPS 域名证书的剩余有效期，按紧急程度（7 天内紧急、30 天内警告、30 天以上正常）排序生成 Markdown 表格报告与 JSON 结构化数据，并附各平台（Let's Encrypt、阿里云、腾讯云、华为云）证书续签操作指引。适用于运维巡检、定期证书盘点、交接环境摸底等场景。触发短语：检查证书到期、SSL 巡检、证书快过期、批量检查证书、证书到期检查、cert expiry monitor、check cert expiry、ssl certificate monitor、tls certificate check。仅做检查与报告，不自动执行续签。"
agent_created: true
---

# SSL Cert Monitor

## Overview

批量检查 HTTPS 域名的 SSL/TLS 证书剩余有效期，按紧急程度排序输出 Markdown 表格报告与 JSON 结构化数据，并附带各平台证书续签操作指引。面向任何 HTTPS 运维场景，不绑定特定云厂商、公司或域名。仅做检查与报告，不自动执行续签。

## 适用场景

- 定期运维巡检，防止证书静默过期导致线上事故
- 批量盘点手头所有域名的证书到期情况，按紧急度排序出清单
- 接手新环境或交接时，快速摸清证书现状
- 证书续签前的现状评估，决定哪些先续、哪些可以后补

## 工作流程

### 1. 获取域名清单

从以下两种输入之一获取待检查的域名清单：

- **CSV 文件**：读取 `assets/domains_template.csv` 格式的清单（字段：`domain,port`，默认端口 443）。适合批量盘点、可版本化复用。
- **对话临时输入**：用户在对话中直接列出域名（如 `reredata.com`、`blog.example.com:8443`），解析后传给检查脚本。适合临时排查。

若用户未指定端口，默认使用 443。

### 2. 执行证书检查

运行 `scripts/check_certs.py`，对清单中每个域名执行：

1. 用 Python 标准库 `ssl` + `socket` 建立 TLS 连接（设置 10 秒超时）
2. 提取对端证书的 `notAfter`（到期时间）、`issuer`（颁发者）、`subject`（主体）、`SAN`（备用域名）
3. 计算剩余天数 = 到期时间 - 当前时间
4. 按紧急程度分级：
   - 🔴 **紧急**：剩余 ≤ 7 天
   - 🟡 **警告**：剩余 ≤ 30 天
   - 🟢 **正常**：剩余 > 30 天
5. 输出 JSON 结构化数据到 `scripts/check_result.json`

**容错处理**：单个域名检查失败（连接超时、DNS 解析失败、证书无效）时，记录错误原因并继续检查下一个，不中断整体流程。

### 3. 生成报告

运行 `scripts/generate_report.py`，读取 `check_result.json`，生成双输出：

- **Markdown 表格报告**：按紧急程度排序（紧急 → 警告 → 正常），包含域名、端口、颁发者、到期日、剩余天数、状态标记、错误信息（若有）。输出到 `scripts/cert_report.md`。
- **JSON 结构化数据**：保留 `check_result.json` 供后续程序消费或接入告警系统。

### 4. 呈现结果与续签指引

将 Markdown 报告呈现给用户，并针对紧急/警告级别的证书：

1. 询问用户是否需要查看对应平台的续签操作指引
2. 若需要，根据证书颁发者匹配 `references/renewal_guide.md` 中的对应章节（Let's Encrypt / 阿里云 / 腾讯云 / 华为云）
3. 给出操作指引要点，**不自动执行续签**

### 5. 后续建议

根据检查结果给出建议：

- 紧急证书：立即续签，附对应平台指引
- 警告证书：安排本周内续签
- 正常证书：下次定期巡检时复查
- 提醒用户可设置定期巡检节奏（建议每周或每两周一次）

## 引用文件

| 文件 | 用途 |
|------|------|
| `scripts/check_certs.py` | 核心检查脚本，读取域名清单，查询证书并输出 JSON |
| `scripts/generate_report.py` | 报告生成脚本，JSON 转 Markdown 表格并按紧急度排序 |
| `references/cert_knowledge.md` | 证书基础知识参考：类型/证书链/SAN/泛域名证书/常见问题排查 |
| `references/renewal_guide.md` | 各平台证书续签操作指引：Let's Encrypt / 阿里云 / 腾讯云 / 华为云 |
| `assets/domains_template.csv` | 域名清单模板（字段：domain,port） |

## 约束与边界

- ✅ 只做检查与报告，**不自动执行续签**
- ✅ 只用 Python 标准库（`ssl` + `socket`），不依赖第三方包
- ✅ 不硬编码任何域名、密钥、账号信息
- ✅ 不绑定特定云厂商或公司
- ✅ 域名清单只在本地处理，不上传任何外部服务，不存储到云端
- ❌ 不处理证书自动部署到 K8s/CDN/Nginx 的动作（属于其他 Skill 范畴）
- ❌ 不存储用户的域名清单到云端（清单只在本地产出与消费）
