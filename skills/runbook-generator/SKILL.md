---
name: ops-fault-runbook
slug: ops-fault-runbook
displayName: 运维故障 Runbook 生成器
version: 1.2.0
description: "运维故障 Runbook 生成器。输入故障特征（如 502/503/504/timeout/DNS解析失败/数据库连接失败/证书过期/pod crashloopbackoff/pod pending/MinIO S3 500/磁盘满/OOM/Docker容器无法启动/Nginx配置错误/K8s节点NotReady/MySQL慢查询/Redis内存满/Ingress不通/Jenkins构建失败/镜像拉取失败/CPU过高/日志目录满），自动匹配预置实战 runbook，输出结构化排查步骤+验证命令+回退方案+根因假设。未匹配时推荐最接近的 runbook 并给出通用排查框架。触发短语：'故障排查'、'runbook'、'排查步骤'、'怎么排查'、'故障处理流程'、'troubleshoot runbook'、'incident playbook'、'生成排查手册'。面向运维工程师、SRE、技术支持、私有化交付。纯规则引擎，不调 AI API，零成本零延迟。本 Skill 是运维全生命周期四件套之一（预防→发现→上报→解决）。"
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

这是运维全生命周期四件套之一，覆盖"解决"环节：
- **ops-backup-checker**（预防）→ 备份健康巡检，防止"以为备份了其实没备"
- **ssl-cert-monitor**（发现）→ 批量检查证书到期
- **issue-report-formatter**（上报）→ 把故障描述整理成标准上报报告
- **ops-fault-runbook**（解决）→ 匹配排查步骤引导解决

四件套覆盖运维全生命周期：预防→发现→上报→解决。

---

## 对话使用示例（用户怎么用）

**你不需要去终端敲命令。** 装了这个 Skill 后，直接在对话里用自然语言描述故障，WorkBuddy 会自动识别触发短语并加载本 Skill。

### 场景 1 · 生产故障发生时（最常用）

你在工作时碰到问题，直接在对话里描述现象：

> **你说**：生产环境有个 pod 一直 crashloopbackoff，帮我看下怎么排查

WorkBuddy 识别到「crashloopbackoff」「排查」触发本 Skill，内部匹配到 `pod-crashloopbackoff` runbook，直接输出：
- 故障概述 + 根因假设树（按概率排序）
- 6 步排查步骤（每步含可直接复制的命令 + 预期输出 + 判断条件）
- 验证方法 + 回退方案

你照着步骤一步步执行，每步的命令可以直接复制到终端跑。

### 场景 2 · 只给故障码或关键词

> **你说**：502

匹配到 `http-502` runbook，输出完整的 502 排查流程。

> **你说**：证书过期了怎么处理

匹配到 `cert-expiry` runbook，输出证书更新 + K8s secret 替换 + CDN 同步的完整步骤。

### 场景 3 · 不确定是哪种故障

> **你说**：连不上数据库

匹配到 `db-connection-failure` runbook。如果你的描述没精确命中任何预置 runbook，会输出「最接近的 3 个 runbook 推荐 + 通用排查框架」，你再选一个或换关键词。

### 场景 4 · 先看看有哪些故障能查

> **你说**：runbook 列表 / 都有哪些排查手册

输出全部 23 个内置 runbook 的清单（ID + 故障类型 + 关键词），你看到接近的再用 `--detail <id>` 或直接描述现象触发。

### 场景 5 · 新人学习常见故障排查流程

> **你说**：给我讲讲 504 怎么排查 / pod pending 一般是什么原因

匹配到对应 runbook，新人可以照着根因假设树和排查步骤学习标准流程，不用等真的出故障才学。

---

## 工作流程

### Step 1 · 识别故障特征

用户提供故障关键词或描述。支持两种输入：
- **关键词**：`502`、`503`、`timeout`、`证书过期`、`pod crashloopbackoff`、`OOM`、`磁盘满`、`connection refused`、`MinIO 500`、`node notready`、`mysql 慢查询`、`redis 内存满`、`ingress 不通`、`jenkins 构建失败`、`镜像拉取失败`、`CPU 高`、`日志目录满`
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
| `dns-resolution-failure` | DNS 解析失败 | dns、解析失败、nslookup、coredns |
| `db-connection-failure` | 数据库连接失败 | 数据库连接失败、db connection、too many connections |
| `pod-pending` | K8s Pod Pending | pod pending、调度失败、unschedulable |
| `docker-container-start-failure` | Docker 容器无法启动 | docker 启动失败、容器启动即退出、exited immediately |
| `nginx-config-error` | Nginx 配置语法错误 | nginx -t、syntax error、nginx reload、nginx 配置 |
| `k8s-node-notready` | K8s 节点 NotReady | node notready、notready、节点异常 |
| `mysql-slow-query` | MySQL 慢查询 | mysql 慢查询、slow query、慢 sql、查询慢 |
| `redis-memory-full` | Redis 内存满/OOM | redis 内存满、redis oom、memory full、maxmemory |
| `ingress-not-working` | K8s Ingress 访问不通 | ingress、ingress 访问不到、域名访问不到 |
| `jenkins-build-failure` | Jenkins 构建失败 | jenkins、构建失败、build failed、pipeline 失败 |
| `docker-image-pull-failure` | Docker 镜像拉取失败 | imagepullbackoff、镜像拉取失败、docker pull |
| `high-cpu-usage` | CPU 使用率过高 | cpu 高、cpu 100%、cpu 打满、cpu 占用 |
| `log-disk-full` | 日志目录磁盘满 | 日志目录满、log 目录满、var log 满、日志过大 |

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
