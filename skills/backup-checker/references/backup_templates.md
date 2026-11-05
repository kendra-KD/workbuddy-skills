# 备份检查模板库

> 5 类开箱即用的备份检查模板，覆盖运维最常见备份类型。
> 每个模板含检查要点、默认阈值、适用场景、CSV 配置示例。

---

## 模板 1 · `mysql-dump` — MySQL 逻辑备份

**检查要点**：
- 备份文件存在（通常为 `.sql.gz` 或 `.sql`）
- 文件大小 ≥ 10MB（MySQL dump 通常不会小于这个值，除非是空库）
- 文件在 24 小时内更新（每日备份场景）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 10 | 小于此值视为异常（疑似空备份/失败） |
| `expected_max_age_hours` | 24 | 超过此时间未更新视为过期 |

**适用场景**：MySQL 定时逻辑备份（mysqldump/xtrabackup 物理备份也可套用，调整阈值即可）。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
db1-mysql-dump,local-file,/data/backups/db1.sql.gz,db1.example.com,10,24
```

---

## 模板 2 · `pg-dump` — PostgreSQL 逻辑备份

**检查要点**：
- 备份文件存在（`.dump` 或 `.sql`）
- 文件大小 ≥ 5MB
- 文件在 24 小时内更新

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 5 | PG dump 通常比 MySQL 小，阈值调低 |
| `expected_max_age_hours` | 24 | - |

**适用场景**：PostgreSQL pg_dump 定时备份。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
pg-main-dump,local-file,/var/backups/pg/main.dump,pg.example.com,5,24
```

---

## 模板 3 · `redis-rdb` — Redis RDB 快照

**检查要点**：
- `dump.rdb` 文件存在
- 文件大小 ≥ 1MB（空 Redis 实例的 RDB 也很小，但生产环境通常 ≥ 1MB）
- 文件在 24 小时内更新（取决于 save 策略）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 1 | - |
| `expected_max_age_hours` | 24 | 若 save 策略较宽松可调到 48-72 |

**适用场景**：Redis 持久化 RDB 文件健康检查。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
redis-cache-rdb,local-file,/var/lib/redis/dump.rdb,redis.example.com,1,24
```

---

## 模板 4 · `nginx-config-tar` — Nginx 配置打包备份

**检查要点**：
- `.tar.gz` 存在
- 文件大小 ≥ 1KB（配置文件很小，但不应为空）
- 文件在 168 小时（7 天）内更新（配置变更频率低，阈值放宽）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 0.001 | 1KB，配置文件本就小 |
| `expected_max_age_hours` | 168 | 7 天，配置备份频率低 |

**适用场景**：Nginx/Apache 配置定时打包备份检查。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
nginx-conf-bk,local-file,/data/backups/nginx-conf.tar.gz,web1.example.com,0.001,168
```

---

## 模板 5 · `minio-bucket` — MinIO/S3 桶备份

**检查要点**：
- 桶/prefix 下有对象（数量 ≥ 1）
- 最新对象在 24 小时内上传

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_objects` | 1 | 桶内至少有 1 个对象 |
| `expected_max_age_hours` | 24 | 最新对象时间戳 |

**适用场景**：MinIO/S3 对象存储备份桶健康检查。

**CSV 配置示例**：
```csv
name,type,path,expected_min_objects,expected_max_age_hours
daily-backup-bucket,minio-s3,s3://daily-backups/,1,24
```

**注意**：MinIO/S3 检查依赖 `mc` 或 `aws-cli`，使用前需配置：
- `mc alias set <alias> <endpoint> <access-key> <secret-key>`
- 或 `aws configure` + 设置 `BACKUP_CHECKER_S3_ENDPOINT` 环境变量（自定义 endpoint）

---

## 模板 6 · `etcd-snapshot` — K8s etcd 快照备份（v1.1 新增）

**检查要点**：
- `.db` 快照文件存在（etcdctl snapshot save 产物，通常路径 `/var/lib/etcd/snapshot.db` 或备份目录）
- 文件大小 ≥ 10MB（空 etcd 快照也不会这么小）
- 文件在 24 小时内更新（etcd 备份应每日执行，集群变更频繁时更短）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 10 | etcd 数据量通常 ≥ 几十 MB |
| `expected_max_age_hours` | 24 | 建议每日备份 |

**适用场景**：K8s 集群 etcd 数据快照健康检查。etcd 是 K8s 的"数据库"，丢了等于整个集群状态丢失——这是集群恢复的底线，必须巡检。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
k8s-etcd-snapshot,local-file,/data/backups/etcd/snapshot.db,master1.example.com,10,24
```

**注意**：etcd 快照通常存在 master 节点上，SSH 检查时 host 填 master 节点地址。

---

## 模板 7 · `k8s-configmap-secret` — K8s 配置资源备份（v1.1 新增）

**检查要点**：
- ConfigMap/Secret 资源在集群中存在（kubectl get 确认）
- 资源未被误删除（备份策略：定期 kubectl export 导出 YAML 存 git，这里检查资源本身是否还在）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_max_age_hours` | 0 | 0=不检查年龄（配置资源可能创建很久，只要存在即可） |

**适用场景**：K8s 集群关键 ConfigMap/Secret 存在性巡检。Secret 被误删是高频事故（如 TLS 证书 secret 被清理导致 ingress 全挂），本模板用 k8s-resource 检查器确认资源健在。

**CSV 配置示例**：
```csv
name,type,path,namespace,expected_max_age_hours
tls-cert-secret,k8s-resource,secret/reredata-tls,enableai,0
core-configmap,k8s-resource,configmap/core-config,enableai,0
minio-config,k8s-resource,configmap/minio-config,wuwen,0
```

**注意**：path 格式为 `resource_type/resource_name`（如 `configmap/core-config`、`secret/tls-cert`）。namespace 必填。资源年龄默认不检查（配置类资源可长期不变）。

---

## 模板 8 · `k8s-volumesnapshot` — K8s PV 卷快照备份（v1.1 新增）

**检查要点**：
- VolumeSnapshot 资源存在（kubectl get volumesnapshot 确认）
- 快照在预期时间内创建（如每日快照策略）

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_max_age_hours` | 24 | 每日快照策略；如周快照则调到 168 |

**适用场景**：云原生 PV 数据备份健康检查。VolumeSnapshot 是 CSI 标准的存储快照机制，适用于有状态应用（数据库/MinIO/消息队列）的 PV 数据备份。

**CSV 配置示例**：
```csv
name,type,path,namespace,expected_max_age_hours
mysql-pv-snapshot,k8s-resource,volumesnapshot/mysql-daily,enableai,24
redis-pv-snapshot,k8s-resource,volumesnapshot/redis-daily,wuwen,24
```

**注意**：path 格式为 `volumesnapshot/<snapshot-name>`。需集群已安装 VolumeSnapshotClass（CSI 驱动支持）。

---

## 模板 9 · `mongodb-dump` — MongoDB 逻辑备份（v1.1 新增）

**检查要点**：
- 备份文件存在（`mongodump` 产物，通常 `.gz` 归档或 `.bson` 目录）
- 文件大小 ≥ 10MB（生产 MongoDB 备份通常更大）
- 文件在 24 小时内更新

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 10 | MongoDB 备份通常 ≥ 几十 MB |
| `expected_max_age_hours` | 24 | - |

**适用场景**：MongoDB 定时逻辑备份（mongodump --archive --gzip 产物）健康检查。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
mongo-main-dump,local-file,/data/backups/mongo/main.gz,mongo1.example.com,10,24
```

**注意**：mongodump 归档文件（`--archive --gzip`）是单文件 `.gz`；目录模式（不带 `--archive`）则产出 `.bson` 文件目录，检查目录下文件数需自定义。本模板针对归档模式。

---

## 模板 10 · `clickhouse-backup` — ClickHouse 备份（v1.1 新增）

**检查要点**：
- 备份归档文件存在（`clickhouse-backup` 工具产物，通常 `.zip`）
- 文件大小 ≥ 50MB（ClickHouse 数据量通常较大）
- 文件在 24-48 小时内更新

**默认阈值**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expected_min_size_mb` | 50 | ClickHouse 列存数据压缩后仍较大 |
| `expected_max_age_hours` | 24 | 全量备份每日，增量可更频繁 |

**适用场景**：ClickHouse 数据库备份（clickhouse-backup 工具 / ALTER TABLE ... FREEZE 产物）健康检查。ClickHouse 常用于日志/分析场景，数据量大，备份完整性尤其重要。

**CSV 配置示例**：
```csv
name,type,path,host,expected_min_size_mb,expected_max_age_hours
ch-events-backup,local-file,/var/lib/clickhouse-backup/events.zip,ch1.example.com,50,24
```

**注意**：clickhouse-backup 工具默认存 `/var/lib/clickhouse-backup/`。如果是 `FREEZE` 产物则是分片目录，检查方式需调整为目录模式（自定义 min_objects 或检查 marker 文件）。

---

## 自定义模板

以上 10 类是开箱即用模板。如果你的备份类型不在其中（如 ES snapshot、TiDB BR、Nacos 配置导出），可以：

1. 确定备份产物形态（文件/对象/K8s 资源）
2. 选择最接近的 type（local-file / minio-s3 / database / k8s-resource）
3. 调整 `expected_min_size_mb` 和 `expected_max_age_hours` 阈值
4. 写进 CSV 清单即可

无需改代码，模板的"内容"部分通过 CSV 参数化实现。

> **v1.1 新增**（2026-11-05）：以下模板 6-10 为 v1.1 扩展，基于 v1.0 下载数据驱动（backup-checker 增速最快 +160%，验证预防方向需求被低估）。新增覆盖 K8s 集群核心（etcd/ConfigMap/PV 快照）+ MongoDB + ClickHouse，补全云原生全栈备份场景。
