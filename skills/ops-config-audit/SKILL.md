---
name: ops-config-audit
slug: ops-config-audit
displayName: 运维配置审计器
version: 1.0.0
description: "运维配置审计器。检查 Nginx upstream 与后端 service 是否一致、SSL 证书与 ingress 域名是否匹配、K8s ConfigMap/Secret/Deployment 配置是否漂移。输入目标环境或配置文件，输出风险等级+修复建议。纯规则引擎，不调用 AI API，零成本零延迟。触发短语：'配置审计'、'检查一下配置'、'config audit'、'nginx 配置检查'、'ssl 证书和域名是否匹配'、'k8s 配置漂移'。本 Skill 是运维全生命周期四件套的前置环节（预防→发现→上报→解决）。"
agent_created: true
---

# 运维配置审计器

## Overview

配置错误是生产事故的重要根因之一：Nginx upstream 指向了不存在的后端、SSL 证书和 ingress 域名不匹配、K8s ConfigMap 改了但 Deployment 没重启……这些问题靠人工巡检容易遗漏。

这个 Skill 把**配置一致性检查**自动化：输入目标环境或配置文件，自动比对多个来源的配置是否一致，输出风险等级和修复建议。

## 解决什么痛点

- 改了 K8s ConfigMap 但忘记重启/重载应用
- Nginx 配置里的 upstream 和实际 service 不一致
- SSL 证书只更新了 secret 但 ingress 还在用旧 secret
- 多环境配置（dev/staging/prod）互相漂移
- 接手新环境时快速发现配置隐患

## 核心能力

1. **Nginx 配置审计**：检查 `proxy_pass` 的 upstream/service 是否真实存在
2. **SSL 证书审计**：检查证书 CN/SAN 是否覆盖 ingress 配置的域名
3. **K8s 配置漂移审计**：比较 ConfigMap/Secret 的当前值与期望值的差异
4. **多环境一致性审计**：对比 dev/staging/prod 的关键配置是否一致
5. **报告输出**：Markdown 表格 + JSON，含风险等级（🔴 高 / 🟡 中 / 🟢 低）

## 产品矩阵定位

运维全生命周期五件套的前置环节：

- **ops-config-audit**（配置审计）→ 在故障发生前发现配置风险
- **ops-backup-checker**（预防）→ 备份健康巡检
- **ssl-cert-monitor**（发现）→ 批量检查证书到期
- **issue-report-formatter**（上报）→ 把故障描述整理成标准上报报告
- **ops-fault-runbook**（解决）→ 匹配排查步骤

## 对话使用示例（用户怎么用）

**场景 1 · 接手新环境时做配置审计**

> **你说**：帮我审计一下 production 环境的配置

输出配置审计报告，列出 Nginx / SSL / K8s 三类配置风险。

**场景 2 · 检查 Nginx 配置是否有指向不存在的服务**

> **你说**：检查一下 nginx 配置里的 upstream 是否和后端服务一致

输出 Nginx 配置审计结果。

**场景 3 · 检查 SSL 证书和域名是否匹配**

> **你说**：ssl 证书和 ingress 域名是否匹配

输出 SSL 证书与 ingress 域名的匹配情况。

**场景 4 · 检查 K8s 配置是否漂移**

> **你说**：检查一下 k8s 的 configmap 和 deployment 是否漂移

输出 ConfigMap/Secret/Deployment 的漂移检测结果。

**场景 5 · 审计本地配置文件**

> **你说**：审计一下 ./configs 目录下的配置文件

输出本地文件级审计结果。

---

## 支持的审计项

| 审计项 | 说明 | 所需输入 |
|--------|------|---------|
| `nginx-upstream` | Nginx upstream 与后端 service 一致性 | nginx 配置文件或目录 |
| `ssl-cert-match` | SSL 证书 CN/SAN 与域名匹配度 | 证书文件 + 域名清单 |
| `k8s-configmap-drift` | ConfigMap 当前值 vs 期望值 | 当前 YAML + 期望 YAML |
| `k8s-secret-drift` | Secret 是否存在/键值是否匹配 | 当前 YAML + 期望 YAML |
| `k8s-ingress-cert` | Ingress TLS secret 与域名是否匹配 | `kubectl get ingress` + secret |
| `multi-env-diff` | 多环境同一份配置的差异 | dev/staging/prod 三个配置文件 |

---

## 输出示例

| 风险等级 | 审计项 | 问题 | 修复建议 |
|---------|--------|------|---------|
| 🔴 高 | nginx-upstream | upstream `backend-api` 指向的 service `api-svc:8080` 不存在 | 检查 service 名/端口是否正确 |
| 🟡 中 | ssl-cert-match | 证书 SAN 缺少 `*.example.com` | 重新申请或更新证书 |
| 🟢 低 | k8s-configmap-drift | ConfigMap `app-config` 的 `log_level` 从 `info` 变为 `debug` | 确认是否为预期变更 |

---

## 文件结构

```
ops-config-audit/
├── SKILL.md
├── scripts/
│   ├── config_audit.py      # 主入口脚本
│   ├── nginx_audit.py        # Nginx 配置审计
│   ├── ssl_audit.py          # SSL 证书审计
│   └── k8s_audit.py          # K8s 配置漂移审计
├── assets/
│   └── domains_template.csv  # 域名清单模板
└── references/
    ├── audit_guide.md        # 审计方法论
    └── check_templates.md    # 检查模板说明
```

---

## 工作原理

1. **解析输入**：根据审计项解析配置文件、K8s YAML、`kubectl` 输出或 CSV 清单
2. **抽取关键字段**：upstream、server_name、listen、证书 CN/SAN、ConfigMap key/value 等
3. **交叉比对**：将配置 A 与配置 B 进行一致性检查
4. **评估风险**：按规则给出高/中/低风险
5. **生成报告**：Markdown 表格 + JSON，含修复建议

---

## 边界说明

- **只读审计**，不会修改任何配置
- 不连接真实数据库/不登录服务器，只分析用户提供的配置文件或命令输出
- 需要用户提供真实配置文件或 `kubectl`/`openssl` 输出作为输入
- 复杂的 Nginx 动态配置（如变量拼接的 proxy_pass）可能无法精确解析

## 定价与变现

本 Skill **免费使用**。如需针对具体业务场景的定制化审计规则或运维代维服务，可通过公众号「不宕机日常」联系。
