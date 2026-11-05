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
