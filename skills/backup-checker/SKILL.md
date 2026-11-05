---
name: ops-backup-checker
slug: ops-backup-checker
displayName: 备份健康巡检器
version: 1.1.0
description: "备份健康巡检工具。批量检查服务器本地备份文件、MinIO/S3 对象存储备份、数据库备份状态（MySQL dump/PG dump/Redis RDB/MongoDB dump）、K8s 资源备份（ConfigMap/Secret/PV 快照/etcd 快照），验证文件存在/大小/时间戳是否符合预期，按健康度（缺失/过期/异常小/正常）排序生成 Markdown 报告与 JSON 数据。内置 10 类常见备份检查模板。触发短语：'备份检查'、'备份巡检'、'备份健康'、'验证备份'、'backup health'、'backup checker'、'备份是否正常'。面向运维、SRE、DBA、私有化交付。只读不写，不执行备份，不存储备份内容。纯 Python 标准库 + mc/aws-cli/ssh，零第三方依赖。"
agent_created: true
---

# Backup Checker · 备份健康巡检器

## Overview

批量检查运维环境中的备份健康度——服务器本地备份文件、MinIO/S3 对象存储备份、数据库备份状态、K8s 资源备份，验证文件存在性、大小合理性、时间戳新鲜度，按健康度排序输出 Markdown 报告与 JSON 数据，并内置 10 类常见备份的检查模板。面向任何运维备份场景，不绑定特定云厂商或公司。**只读不写，不执行备份，不存储备份内容**。

**解决什么痛点**：运维最怕的不是"没备份"，而是"以为备份了，真出事才发现备份是坏的/过期的/路径错的/大小异常的"。手动 SSH 一台台翻备份目录既慢又容易漏，且没法标准化巡检。这个 Skill 把备份巡检标准化：一份 CSV 巡检清单进去，一份按健康度排序的巡检报告出来，30 秒扫完所有备份目标，任何环境都能跑。

**核心能力**：
1. **多目标检查**：支持本地文件系统备份（SSH 拉取元信息）、MinIO/S3 对象存储备份（mc/aws-cli CLI）、数据库备份状态（MySQL/PG dump 文件）、K8s 资源备份（kubectl 导出 YAML）
2. **健康度分级**：🔴缺失（备份不存在）/ 🟡过期（时间戳超期）/ 🟠异常（大小异常小，疑似空备份）/ 🟢正常，按严重度排序输出
3. **双输出格式**：Markdown 表格报告（人类阅读，可直接复制到企业微信/钉钉）+ JSON 结构化数据（程序化消费，便于接入告警/知识库）
4. **10 类内置模板**：MySQL dump / PG dump / Redis RDB / Nginx config tar / MinIO bucket / etcd snapshot / K8s ConfigMap-Secret / K8s VolumeSnapshot / MongoDB dump / ClickHouse backup，开箱即用，覆盖数据库+配置+对象存储+K8s 全栈备份场景
5. **零环境依赖**：纯 Python 标准库（os/stat/json/csv/datetime/subprocess），远程拉取调 mc/aws-cli/ssh，不引入第三方 Python 包

**适用场景**：
- 定期运维巡检（周一早巡检、交接班），防止"以为备份了其实没有"
- 批量盘点手头所有服务器的备份健康度，按严重度排序出清单
- 接手新环境或私有化交付时，快速摸清备份现状
- 故障复盘后验证：确认这个服务相关的备份是否真的可用
- 备份策略调整前的现状评估

**不适用场景**：
- 自动执行备份（本 Skill 只检查，不触发备份，避免误覆盖已有数据）
- 备份内容完整性校验（如解压验证/数据库恢复测试，当前只查元信息）
- 实时备份监控（本 Skill 是一次性巡检工具，不是持续监控告警系统）
- 备份文件内容检索（不读取备份内容，只取文件名/大小/时间戳）

---

## 产品矩阵定位

这是运维工具链的第四环，补全"预防"侧：

| 环节 | Skill | 作用 |
|------|-------|------|
| 预防 | **backup-checker**（本 Skill） | 巡检备份是否健康，防患于未然 |
| 发现 | ssl-cert-monitor | 批量检查证书到期 |
| 上报 | issue-report-formatter | 把故障描述整理成标准上报报告 |
| 解决 | ops-fault-runbook | 匹配排查步骤引导解决 |

四件套覆盖运维全生命周期：**预防→发现→上报→解决**。

---

## 对话使用示例（用户怎么用）

**你不需要去终端敲命令。** 装了这个 Skill 后，直接在对话里用自然语言描述需求，WorkBuddy 会自动识别触发短语并加载本 Skill。

### 场景 1 · 周一早巡检（最常用）

周一早上想确认周末备份有没有正常跑：

> **你说**：帮我做一下备份巡检 / 检查备份是否正常

WorkBuddy 识别到「备份巡检」「备份是否正常」触发本 Skill。如果你有 CSV 巡检清单（放在 `assets/backup_targets_template.csv`），它会批量检查所有目标；如果没有，它会问你要检查哪些备份目标（如"db1 的 MySQL dump、minio 的 bucket backup"），然后输出按健康度排序的巡检报告。

### 场景 2 · 故障复盘后验证

刚处理完一次故障，想确认这个服务相关的备份是不是真的可用：

> **你说**：验证一下 db1 的备份能不能用 / 检查 minio bucket backup 健康度

只检查你指定的目标，30 秒出报告。

### 场景 3 · 接手新环境盘点

接手新环境或私有化交付时，第一件事摸清备份现状：

> **你说**：盘点一下这个环境的备份情况 / 备份健康检查

如果你提前准备了 CSV 清单（列出所有备份目标），直接批量扫；没有清单就逐个描述目标，Skill 解析后检查。

### 场景 4 · 只查单个目标（临时排查）

> **你说**：检查 db1 的 MySQL dump，路径 /data/backups/db1.sql.gz，最少 10MB，24 小时内

单个目标检查，立即出结果（正常/过期/异常/缺失）。

---

## 工作流程

### Step 1 · 获取巡检清单

从以下两种输入之一获取待检查的备份目标清单：

- **CSV 文件**：读取 `assets/backup_targets_template.csv` 格式的清单。适合批量盘点、可版本化复用。
- **对话临时输入**：用户在对话中直接描述备份目标（如"检查 db1 的 MySQL dump、检查 minio 的 bucket backup"），解析后传给检查脚本。

CSV 字段说明见 `assets/backup_targets_template.csv` 内注释。

### Step 2 · 执行备份检查

运行 `scripts/check_backups.py`，对清单中每个目标执行：

1. 按 `type` 字段分发到对应检查器（local-file / minio-s3 / database / k8s-resource）
2. 各检查器拉取备份元信息（文件名/大小/修改时间）
3. 与 `expected_*` 字段比对：是否到期（`expected_max_age_hours`）、大小是否异常（`expected_min_size_mb`）
4. 按健康度分级：
   - 🔴 **缺失**：备份文件/对象不存在
   - 🟡 **过期**：时间戳超过 `expected_max_age_hours`
   - 🟠 **异常**：存在但大小 < `expected_min_size_mb`（疑似空备份/失败备份）
   - 🟢 **正常**：存在、未过期、大小合理
5. 输出 JSON 结构化数据到 `scripts/check_result.json`

**容错处理**：单个目标检查失败（SSH 连不上、mc 未安装、权限不足）时，记录错误原因并继续检查下一个，不中断整体流程。

### Step 3 · 生成报告

运行 `scripts/generate_report.py`，读取 `check_result.json`，生成双输出：

- **Markdown 表格报告**：按健康度排序（缺失 → 过期 → 异常 → 正常），包含目标名、类型、路径、大小、最后修改时间、健康状态、错误信息（若有）。输出到 `scripts/backup_report.md`。
- **JSON 结构化数据**：保留 `check_result.json` 供后续程序消费或接入告警系统。

### Step 4 · 呈现结果与建议

将 Markdown 报告呈现给用户，并针对各健康度级别给出建议：

- 🔴 缺失：立即排查备份任务是否在跑，确认备份策略是否生效
- 🟡 过期：确认备份任务卡住或调度异常，检查 cron/定时任务
- 🟠 异常：疑似备份失败（如磁盘满/权限错/数据库锁），查备份日志
- 🟢 正常：下次定期巡检时复查

### 调用示例

```bash
# 方式一：CSV 清单批量检查（推荐，可版本化复用）
python scripts/check_backups.py --csv assets/backup_targets_template.csv --output check_result.json
python scripts/generate_report.py --input check_result.json --output backup_report.md
# 报告输出到 backup_report.md

# 方式二：只检查单个目标（适合临时排查）
python scripts/check_backups.py --single "mysql-dump-db1" --type local-file --path "/data/backups/db1.sql.gz" --host db1 --min-size 10 --max-age 24

# 方式三：只看 JSON 结构化数据（便于接入告警系统）
cat check_result.json
```

**Markdown 报告示例**：
```markdown
| 目标 | 类型 | 路径 | 大小 | 最后修改 | 健康度 | 说明 |
|------|------|------|------|---------|--------|------|
| db1-mysql-dump | local-file | /data/backups/db1.sql.gz | 0 MB | 2026-10-20 | 🟠 异常 | 大小低于阈值 10MB |
| minio-bucket-bk | minio-s3 | s3://backups/daily/ | 256 MB | 2026-10-31 | 🟢 正常 | - |
| app-configmap | k8s-resource | production/app-config | - | 2026-10-31 | 🟢 正常 | - |
```

---

## 内置备份检查模板

10 类开箱即用的检查模板，覆盖运维最常见备份类型。详见 `references/backup_templates.md`。

> v1.1 扩展至 10 类（2026-11-05），基于下载数据驱动（backup-checker 增速最快 +160%），新增 K8s 集群核心（etcd/ConfigMap/PV 快照）+ MongoDB + ClickHouse，覆盖云原生全栈备份场景。

| 模板 ID | 备份类型 | 检查要点 | 默认阈值 |
|---------|---------|---------|---------|
| `mysql-dump` | MySQL 逻辑备份 | .sql.gz 文件存在 + 大小 ≥ 10MB + 24h 内更新 | min_size=10MB, max_age=24h |
| `pg-dump` | PostgreSQL 逻辑备份 | .dump/.sql 文件存在 + 大小 ≥ 5MB + 24h 内更新 | min_size=5MB, max_age=24h |
| `redis-rdb` | Redis RDB 快照 | dump.rdb 文件存在 + 大小 ≥ 1MB + 24h 内更新 | min_size=1MB, max_age=24h |
| `nginx-config-tar` | Nginx 配置打包备份 | .tar.gz 存在 + 大小 ≥ 1KB + 168h(7天) 内更新 | min_size=1KB, max_age=168h |
| `minio-bucket` | MinIO/S3 桶备份 | 桶内最新对象时间戳 + 对象数量 ≥ 1 | max_age=24h |
| `etcd-snapshot` | K8s etcd 快照（v1.1新增） | .db 文件存在 + 大小 ≥ 10MB + 24h 内更新 | min_size=10MB, max_age=24h |
| `k8s-configmap-secret` | K8s ConfigMap/Secret（v1.1新增） | 资源存在性巡检（防误删） | max_age=0(不查年龄) |
| `k8s-volumesnapshot` | K8s PV 卷快照（v1.1新增） | VolumeSnapshot 资源存在 + 24h 内创建 | max_age=24h |
| `mongodb-dump` | MongoDB 逻辑备份（v1.1新增） | .gz 归档存在 + 大小 ≥ 10MB + 24h 内更新 | min_size=10MB, max_age=24h |
| `clickhouse-backup` | ClickHouse 备份（v1.1新增） | .zip 归档存在 + 大小 ≥ 50MB + 24h 内更新 | min_size=50MB, max_age=24h |

---

## 引用文件

| 文件 | 用途 |
|------|------|
| `scripts/check_backups.py` | 核心检查脚本，读取巡检清单，检查各备份目标并输出 JSON |
| `scripts/generate_report.py` | 报告生成脚本，JSON 转 Markdown 表格并按健康度排序 |
| `references/backup_templates.md` | 5 类内置备份检查模板详解（检查要点/默认阈值/适用场景） |
| `references/setup_guide.md` | 环境准备指引（mc/aws-cli/ssh/kubectl 安装与配置） |
| `assets/backup_targets_template.csv` | 巡检清单模板（含字段说明注释） |

---

## 约束与边界

### 安全红线
1. **只读不写**：只检查备份元信息，绝不执行备份、绝不写入备份目标、绝不删除任何文件
2. **不存储备份内容**：只取文件名/大小/时间戳，不读取备份文件内容（避免敏感数据泄露）
3. **不硬编码任何凭据**：SSH 密钥、MinIO access key、数据库密码等一律走环境变量或用户配置，不写进脚本
4. **不自动执行备份**：检查与备份任务解耦，避免巡检脚本误触发备份覆盖已有数据
5. **远程拉取只读**：SSH/mc/aws-cli/kubectl 调用只用 ls/stat/head 等只读命令，不用任何写入命令

### 适用边界
- 适合：定期备份巡检、批量备份盘点、交接环境摸底、故障复盘后验证
- 不适合：自动执行备份、备份内容完整性校验（解压/恢复测试）、实时备份监控、备份内容检索
