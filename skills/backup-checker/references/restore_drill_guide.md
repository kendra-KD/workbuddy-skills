# 恢复演练指南（Restore Drill）

> v1.2 新增能力。备份巡检只回答「备份在不在」，恢复演练回答「备份能不能恢复」。

## 为什么需要恢复演练

运维最常见的误判：

| 表象 | 真相 |
|------|------|
| `ls -lh` 显示 db1.sql.gz 有 128MB，时间戳是今天 | 文件是截断的，gzip 解压到 60% 就报错 |
| 巡检报告全绿 | dump 是空的（0 条 SQL），恢复后数据库是空的 |
| 文件大小正常 | 文件是预分配的全零块，磁盘写满时的失败产物 |
| RDB 文件存在 | 实际是别的文件改名而来，Redis 起不来 |

这些都是 `check_backups.py` 查不出来的——它只看元信息。恢复演练补上这一层。

## 校验链设计

按文件扩展名自动选择检查链：

| 扩展名 | 检查链 | 判定 |
|--------|--------|------|
| `.sql.gz` / `.dump.gz` | 非空 → gzip CRC → 解压后 SQL 特征 → 非全零 | 关键项任一失败 = 🔴 不可恢复 |
| `.tar.gz` / `.tgz` | 非空 → gzip CRC → tar 目录可读 → 非全零 | 同上 |
| `.zip` | 非空 → zip CRC → 非全零 | 同上 |
| `.sql` / `.dump` | 非空 → SQL 头部特征 → 非全零 | 同上 |
| `.rdb` | 非空 → Redis 文件头（`REDIS`） | 同上 |
| `.db`（etcd） | 非空 → 文件头有效 + 大小合理 → 非全零 | 同上 |
| `.yaml` / `.yml` | 非空 → YAML 可解析 | YAML 失败仅存疑（非关键） |
| 其他 | 非空 → 非全零 | — |

## 检查项详解

### `non_empty`（关键）
文件是否存在且大小 > 0。

### `gzip_stream`（关键）
流式读完整个 gzip，触发 CRC 校验。
- 截断的包 → `Compressed file ended before the end-of-stream marker was reached`
- 非 gzip 文件 → `Not a gzipped file`
- 通过 → 报告解压后大小

**为什么不落地解压**：避免巡检本身占用磁盘，也不产生临时敏感文件。

### `tar_list`（关键）
尝试列出 tar 内所有条目。空 tar 或结构损坏会失败。

### `zip_test`（关键）
调用 `zipfile.testzip()` 逐个校验 CRC。

### `sql_header` / `sql_gz_content`（关键）
在文件前 128KB 内查找 SQL 语句特征：
- `CREATE TABLE`、`INSERT INTO`、`DROP TABLE`
- `-- MySQL dump`、`-- PostgreSQL database dump`
- `COPY `、`SET `、`/*!`、`LOCK TABLES`

这是防「空 dump 假绿」的核心检查——一个压缩率很高但内容是空的 gzip，CRC 会通过，但内容特征检查会失败。

### `redis_rdb`（关键）
检查文件前 5 字节是否为 `REDIS`，后 4 字节为版本号（如 `0011` = RDB v11）。

### `etcd_db`（关键）
- 前 16 字节不能全零
- 文件大小 ≥ 100KB（etcd 快照通常远大于此）

深度验证建议再跑：`etcdctl snapshot status <file>`

### `not_all_zero`（非关键）
前 4KB 如果全是 `0x00`，直接判定坏备份（磁盘满时预分配但未写入的产物）。

### `yaml_parse`（非关键）
用 PyYAML 尝试解析（未安装则跳过）。YAML 解析失败标记为存疑而非不可恢复，因为 K8s YAML 可能有自定义标签。

## 评级规则

| 评级 | 触发条件 | 含义 |
|------|---------|------|
| ✅ **可恢复** | 所有关键检查通过，无失败项 | 可以放心用于恢复 |
| 🟠 **存疑** | 无非关键项失败，但非关键检查失败 | 大概率能恢复，建议人工复核 |
| 🔴 **不可恢复** | 任一关键检查失败 | 直接判定坏备份，需重新备份 |
| ⚪ **未验证** | 文件超过 `--max-read-mb` 限制，所有深度检查跳过 | 需人工验证或调高上限 |

## 深度读取上限

默认 200MB。超过则跳过 `gzip_stream` / `tar_list` / `zip_test` / `sql_gz_content` 等需要读全文件的检查。

**为什么设上限**：一个 50GB 的备份文件完整读一遍可能占用数分钟 IO，影响业务。

**处理方式**：
- 大备份可调高上限：`--max-read-mb 2000`
- 或先用 `check_backups.py` 看元信息，再单独对大文件做恢复演练
- 标记为 ⚪未验证 的目标不会误判为正常，需要人工确认

## 恢复命令参考

每个目标会输出对应的恢复命令模板，例如：

| 类型 | 命令 |
|------|------|
| MySQL | `gunzip -c db1.sql.gz \| mysql -u<user> -p<pass> <database>` |
| PostgreSQL | `pg_restore -U<user> -d <database> db1.dump` |
| Redis | `systemctl stop redis && cp dump.rdb /var/lib/redis/ && chown redis:redis /var/lib/redis/dump.rdb && systemctl start redis` |
| MongoDB | `mongorestore --gzip --archive=backup.gz --drop` |
| ClickHouse | `clickhouse-backup restore <backup-name>` |
| etcd | `etcdctl snapshot restore snapshot.db --data-dir /var/lib/etcd-restored` |
| MinIO | `mc mirror <alias>/<bucket> <target-dir>` |
| K8s | `kubectl apply -f resource.yaml` |
| 文件 | `tar -xzf backup.tar.gz -C <target-dir>` |

⚠️ **这些命令仅供参考，恢复会覆盖数据，执行前必须人工确认目标环境和数据范围。**

## 最佳实践

1. **两级验证工作流**：
   ```bash
   # 第一级：快速巡检（秒级）
   python scripts/check_backups.py --csv targets.csv -o check_result.json
   # 第二级：对 🟢正常 的目标做恢复演练
   python scripts/restore_drill.py --csv targets.csv
   ```

2. **频率建议**：
   - 每日：`check_backups.py`（元信息巡检）
   - 每周：`restore_drill.py`（恢复演练）
   - 每季度：真实恢复演练（选一个非关键服务实际恢复一次）

3. **CI/CD 集成**：把恢复演练挂到备份任务之后，备份完成立即验证，失败即告警——这样坏备份在产生时就被发现，而不是等到真需要恢复时。

4. **不要只看巡检全绿**：巡检绿 + 恢复演练绿 = 备份可信。只有巡检绿是假安全感。

## 已知边界

- **不验证业务语义**：SQL 里有 `CREATE TABLE` 不代表表结构和期望一致，也不代表数据完整（无业务校验）
- **不验证外键/约束**：恢复时可能因约束冲突失败
- **不验证大数据量一致性**：只读前 128KB，如果 dump 前半段正常但后半段截断，gzip CRC 能发现，但内容特征查不出来
- **远程主机需要装工具**：`gzip`/`tar`/`unzip` 必须在远程主机可用
- **YAML 校验需要 PyYAML**：未安装则该项跳过（不影响其他检查）