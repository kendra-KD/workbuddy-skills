# 配置审计模板说明

## nginx-upstream

检查 Nginx 配置中的 `proxy_pass` 是否指向已定义的 `upstream`，以及是否有未使用的 upstream。

输入：
- `--nginx-conf <file|dir>`：单个 nginx.conf 或配置目录

示例：
```bash
python scripts/config_audit.py --type nginx-upstream --nginx-conf /etc/nginx
```

## ssl-cert-match

检查 SSL 证书的 SAN 是否覆盖指定域名。

输入：
- `--cert <path>`：PEM 格式证书文件
- `--domains <csv|domain1,domain2>`：域名清单

示例：
```bash
python scripts/config_audit.py --type ssl-cert-match --cert cert.pem --domains example.com,www.example.com
```

## k8s-configmap-drift

比较当前 ConfigMap YAML 和期望 YAML 的差异。

输入：
- `--current <path>`：当前配置 YAML
- `--expected <path>`：期望配置 YAML

示例：
```bash
python scripts/config_audit.py --type k8s-configmap-drift --current current.yaml --expected expected.yaml
```

## k8s-secret-drift

比较当前 Secret YAML 和期望 YAML 的差异。

输入同 `k8s-configmap-drift`。

## k8s-ingress-cert

检查 Ingress 引用的 TLS secret 是否存在。

输入：
- `--ingress-yaml <path>`：Ingress YAML
- `--secret-yaml <path>`：Secret YAML（可包含多个 secret）

示例：
```bash
python scripts/config_audit.py --type k8s-ingress-cert --ingress-yaml ingress.yaml --secret-yaml secrets.yaml
```

## multi-env-diff

对比多环境配置文件的差异。

输入：
- `--files <path1,path2,path3>`：逗号分隔的文件路径

示例：
```bash
python scripts/config_audit.py --type multi-env-diff --files dev.conf,staging.conf,prod.conf
```

## nginx-ssl-mismatch（v1.1 新增）

检查 Nginx 每个 server 块的 `server_name` 是否被其 `ssl_certificate` 覆盖，
并验证证书与私钥是否成对（modulus 一致）。

输入：
- `--nginx-conf <file|dir>`：单个 nginx.conf 或配置目录

检查项：
| 检查 | 风险 |
|------|------|
| server_name 未被证书 SAN 覆盖 | 🔴 高 |
| 证书文件不存在 | 🔴 高 |
| 证书与私钥 modulus 不匹配 | 🔴 高 |
| 监听 443 但未配置 ssl_certificate | 🟡 中 |
| 证书无法解析（非 PEM/openssl 不可用） | 🟡 中 |

示例：
```bash
python scripts/config_audit.py --type nginx-ssl-mismatch --nginx-conf /etc/nginx
```

支持通配符证书（`*.example.com` 会匹配 `api.example.com`）。
`server_name _;` 和通配符 server_name 会被跳过。

## k8s-resource-limits（v1.1 新增）

检查 Deployment / StatefulSet / DaemonSet / Job / CronJob 的容器是否设置了合理的
resources.requests / limits。

输入：
- `--current <path>`：工作负载 YAML（`--workload` 是别名）

检查项：
| 检查 | 风险 | 说明 |
|------|------|------|
| 完全未设 resources | 🔴 高 | QoS=BestEffort，节点压力时最先被驱逐 |
| limits < requests | 🔴 高 | 非法配置，API Server 可能拒绝 |
| 只设 requests，未设 limits | 🟡 中 | 无上限，可能吃满节点资源 |
| 未设 limits.memory | 🟡 中 | 内存可无限增长触发节点 OOM |
| 未设 requests | 🟡 中 | 调度器无法正确评估资源 |

示例：
```bash
# 先从集群导出
kubectl get deploy,sts,ds -n production -o yaml > workloads.yaml
python scripts/config_audit.py --type k8s-resource-limits --current workloads.yaml
```

支持 initContainers 和 CronJob 的嵌套 jobTemplate 结构。
资源值解析支持 `100m` / `128Mi` / `1Gi` / `1G` 等常见格式。
