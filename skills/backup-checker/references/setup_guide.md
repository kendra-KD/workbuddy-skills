# 环境准备指引

> backup-checker 调用外部 CLI 工具拉取备份元信息，使用前需按检查目标类型准备对应工具。

---

## 按目标类型的工具需求

| 目标类型 | 所需工具 | 必需性 |
|---------|---------|--------|
| `local-file`（远程） | ssh | 必需 |
| `local-file`（本地） | 无（Python os.stat） | - |
| `minio-s3` | mc 或 aws-cli（二选一） | 必需其一 |
| `database` | ssh（远程 dump 文件） | 必需（若 dump 在远程） |
| `k8s-resource` | kubectl | 必需 |

---

## SSH 配置（local-file 远程 / database 远程）

backup-checker 通过 `ssh <host> stat ...` 拉取远程文件元信息。要求：

1. **SSH 免密登录已配置**：`ssh-keygen` + `ssh-copy-id user@host`
2. **BatchMode**：脚本用 `-o BatchMode=yes`，不会弹出密码提示（若未配免密会直接失败，不会挂起）
3. **ConnectTimeout**：默认 10 秒，防卡死

**测试**：
```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 user@host "stat -c '%s %Y' /path/to/backup"
```

若返回 `size mtime` 即可用；若提示密码则需配免密。

---

## MinIO Client (mc) 配置（minio-s3）

**安装**：
```bash
# Linux/Mac
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc && sudo mv mc /usr/local/bin/

# Windows (PowerShell)
Invoke-WebRequest -Uri "https://dl.min.io/client/mc/release/windows-amd64/mc.exe" -OutFile "C:\Windows\mc.exe"
```

**配置 alias**（连接 MinIO/S3 endpoint）：
```bash
mc alias set myminio http://minio.example.com:9000 ACCESSKEY SECRETKEY
```

**环境变量**：backup-checker 默认用 alias 名 `local`。若你的 alias 不同，设置：
```bash
export BACKUP_CHECKER_MC_ALIAS="myminio"
```

**测试**：
```bash
mc ls --recursive --json myminio/daily-backups/
```

若返回 JSON 行（每行一个对象）即可用。

---

## AWS CLI 配置（minio-s3 备选）

若环境无 mc 但有 aws-cli，backup-checker 会自动降级用 aws-cli。

**安装**：
```bash
pip install awscli
# 或
# macOS: brew install awscli
# ubuntu: apt install awscli
```

**配置**：
```bash
aws configure
# 输入 Access Key / Secret Key / Region
```

**自定义 endpoint**（连接 MinIO 或自建 S3）：
```bash
export BACKUP_CHECKER_S3_ENDPOINT="http://minio.example.com:9000"
```

**测试**：
```bash
aws s3api list-objects-v2 --bucket daily-backups --endpoint-url http://minio.example.com:9000
```

---

## kubectl 配置（k8s-resource）

**安装**：参考 [Kubernetes 官方文档](https://kubernetes.io/docs/tasks/tools/)

**配置 kubeconfig**：
```bash
export KUBECONFIG=/path/to/kubeconfig
# 或默认 ~/.kube/config
```

**权限**：检查用的 ServiceAccount 至少需要对目标资源的 `get` 权限。

**测试**：
```bash
kubectl get configmap core-config -n enableai -o json --ignore-not-found
```

---

## 凭据安全

- **SSH 密钥**：用 `~/.ssh/id_*`，不硬编码到脚本或 CSV
- **MinIO/S3 凭据**：通过 `mc alias set` 或 `aws configure` 配置，不写进 CSV
- **数据库密码**：本 Skill 不直接连数据库，只检查 dump 文件，不需要数据库凭据
- **K8s 凭据**：用 kubeconfig，路径走 `KUBECONFIG` 环境变量

**红线**：CSV 清单中只填路径和阈值，不填任何密码/密钥。
