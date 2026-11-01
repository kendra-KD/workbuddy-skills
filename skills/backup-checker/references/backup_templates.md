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

## 自定义模板

以上 5 类是开箱即用模板。如果你的备份类型不在其中（如 MongoDB bsondump、ES snapshot、etcd snapshot），可以：

1. 确定备份产物形态（文件/对象/K8s 资源）
2. 选择最接近的 type（local-file / minio-s3 / database / k8s-resource）
3. 调整 `expected_min_size_mb` 和 `expected_max_age_hours` 阈值
4. 写进 CSV 清单即可

无需改代码，模板的"内容"部分通过 CSV 参数化实现。
