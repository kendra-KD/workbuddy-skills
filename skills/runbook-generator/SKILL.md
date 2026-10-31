---
name: ops-fault-runbook
slug: ops-fault-runbook
displayName: 运维故障 Runbook 生成器
version: 1.0.0
description: "运维故障 Runbook 生成器。输入故障特征（如 502/503/timeout/证书过期/pod crashloopbackoff/MinIO S3 500/磁盘满/OOM），自动匹配预置实战 runbook，输出结构化排查步骤+验证命令+回退方案+根因假设。触发短语：'故障排查'、'runbook'、'排查步骤'、'怎么排查'、'故障处理流程'、'troubleshoot runbook'、'incident playbook'、'生成排查手册'。面向运维工程师、SRE、技术支持、私有化交付等场景。纯规则引擎，不调 AI API，零成本零延迟。"
agent_created: true
---

# Runbook Generator · 运维故障 Runbook 生成器

## Overview

输入故障特征关键词，秒级匹配预置实战 runbook，输出可直接执行的排查步骤、验证命令、回退方案和根因假设。

**解决什么痛点**：运维遇到故障时，要么翻聊天记录找上次怎么排查的，要么凭记忆从零想步骤，容易漏关键验证步骤、漏回退方案。新人接手更痛苦——老员工脑子里的排查经验没法传承。这个 Skill 把实战排查经验固化成可复用的 runbook，故障发生时一键调出。

**核心能力**：
1. **特征匹配**：输入故障关键词（如"502"、"证书过期"、"pod crashloopbackoff"）→ 自动匹配最相关的预置 runbook
2. **结构化输出**：每个 runbook 含排查步骤（含命令）+ 预期输出 + 验证方法 + 回退方案 + 根因假设树
3. **多 runbook 列表**：`--list` 查看所有可用 runbook，`--detail <名称>` 查看单个完整 runbook
4. **双输出格式**：Markdown（人类阅读，可直接复制）+ JSON（程序化消费，便于知识库沉淀）

**适用场景**：
- 生产故障发生时，快速调出对应 runbook 照着排查
- 新人 onboarding，学习常见故障的标准排查流程
- 值班交接时，把 runbook 作为交接材料的一部分
- 私有化交付时，把 runbook 作为交付物给客户运维团队
- 故障复盘后，把新总结的排查经验沉淀成新 runbook

**不适用场景**：
- 没有预置 runbook 的故障类型（会输出通用排查框架，但不如预置的精准）
- 需要实时诊断的动态故障（本 Skill 是静态规则库，不读取实时监控数据）
- 非运维场景的通用问题排查（如代码 bug 调试，不适用）

## 产品矩阵定位

这是运维工具链的第三环：
- **ssl-cert-monitor**（发现问题）→ 批量检查证书到期
- **issue-report-formatter**（上报问题）→ 把故障描述整理成标准上报报告
- **runbook-generator**（解决问题）→ 匹配排查步骤引导解决

三件套覆盖了运维故障的完整生命周期。

## 工作流程

### Step 1 · 识别故障特征

用户提供故障关键词或描述。支持两种输入：
- **关键词**：`502`、`503`、`timeout`、`证书过期`、`pod crashloopbackoff`、`OOM`、`磁盘满`、`connection refused`、`MinIO 500`
- **自然语言**：`生产环境 502 了`、`有个 pod 一直 crashloopbackoff`、`证书快过期了怎么处理`

### Step 2 · 匹配预置 Runbook

```bash
# 方式一：关键词匹配
python scripts/runbook_matcher.py 502
python scripts/runbook_matcher.py "pod crashloopbackoff"

# 方式二：自然语言匹配
echo "生产环境 502 了" | python scripts/runbook_matcher.py

# 方式三：查看所有可用 runbook
python scripts/runbook_matcher.py --list

# 方式四：查看单个 runbook 完整内容
python scripts/runbook_matcher.py --detail http-502
```

### Step 3 · 执行排查

匹配到的 runbook 会输出：
1. **故障概述**：什么情况、常见根因
2. **排查步骤**：按顺序执行，每步含命令 + 预期输出 + 判断条件
3. **验证方法**：确认故障是否解决
4. **回退方案**：排查过程中如果操作有副作用，怎么回退
5. **根因假设树**：按概率排序的可能原因，逐个验证

### Step 4 · 扩展自定义 Runbook（可选）

用户可以把团队内部积累的排查经验沉淀成新 runbook，放入 `references/custom_runbook_guide.md` 指引的自定义目录。详见该文档。

## 内置 Runbook 清单

| ID | 故障类型 | 关键词 |
|----|----------|--------|
| `http-502` | 502 Bad Gateway | 502、bad gateway、网关错误 |
| `http-503` | 503 Service Unavailable | 503、service unavailable、服务不可用 |
| `http-504` | 504 Gateway Timeout | 504、gateway timeout、网关超时 |
| `timeout` | 连接超时 | timeout、超时、connection timed out |
| `connection-refused` | 连接被拒 | connection refused、连接拒绝、ECONNREFUSED |
| `cert-expiry` | SSL 证书过期 | 证书过期、cert expired、ssl error |
| `pod-crashloopbackoff` | Pod CrashLoopBackOff | crashloopbackoff、pod crash、容器重启 |
| `minio-s3-500` | MinIO/S3 返回 500 | minio 500、s3 error、presigned url |
| `disk-full` | 磁盘空间满 | disk full、no space、磁盘满 |
| `oom-killed` | OOM Killed | oom、out of memory、内存溢出 |

## 输出格式

### Markdown（默认）

```bash
python scripts/runbook_matcher.py 502
```

输出可直接复制到企业微信/钉钉/邮件的 Markdown 排查报告。

### JSON

```bash
python scripts/runbook_matcher.py 502 --format json
```

输出结构化数据，便于知识库沉淀或批量统计。

## 安全边界

- **只输出排查步骤，不自动执行命令**：所有命令需要人工确认后执行
- **回退方案必含**：每步有副作用的操作都配回退方案
- **不诊断未预置的故障**：未匹配到 runbook 时输出通用排查框架，不臆造步骤
- **不读取实时数据**：不连监控、不读日志、不访问集群，纯静态规则库

## 变现引导

本 Skill 免费使用。如果你需要：
- **定制专属 runbook**（把你们团队的排查经验固化成 runbook）→ 公众号「不宕机日常」联系
- **运维代维服务**（专业运维团队代管服务器/集群）→ 公众号「不宕机日常」联系
- **私有化交付排障手册**（给客户交付一套完整 runbook）→ 公众号「不宕机日常」联系
