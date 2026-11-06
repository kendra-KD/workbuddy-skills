# Growth Log — ops-config-audit

## #001 · 2026-11-05 · 首次创建（v1.0）

### 触发场景
四件套（预防→发现→上报→解决）已形成闭环，但用户希望扩展 skill 类型和范围。运维配置错误是生产事故的重要根因，决定在「预防」前再增加一层「配置审计」。

### 方案选择
- **能力边界**：输入目标环境或配置文件，自动检查 Nginx upstream、SSL 证书、K8s ConfigMap/Secret/Ingress、多环境配置一致性
- **输入方式**：命令行参数，支持单个文件/目录/YAML
- **输出格式**：Markdown 表格 + JSON
- **技术栈**：Python 标准库 + PyYAML，只读审计
- **作用域**：项目级（副业产品，可分发）
- **Fork/从零**：从零设计

### 最终效果
- v1.0 支持 6 种审计类型：
  - nginx-upstream
  - ssl-cert-match
  - k8s-configmap-drift
  - k8s-secret-drift
  - k8s-ingress-cert
  - multi-env-diff

### 关键决策
1. **纯规则引擎不调 AI API**：和四件套保持一致，零成本零延迟。
2. **只读审计不修改配置**：避免误操作风险。
3. **风险等级分级**：高/中/低三级，便于用户优先处理。

---

## #002 · 2026-11-06 · v1.1 升级（补 Nginx 证书错配 + K8s 资源限制）

### 触发场景
v1.0 发布后首日下载 7 次，冷启动表现不错。用户指出两个高频但未覆盖的审计场景：
- **nginx-ssl-mismatch**：`ssl-cert-match` 是从「证书 + 域名清单」正向比对，但运维更常见的场景是「nginx 里配了一堆 server_name，忘了某个域名不在证书 SAN 里」，上线后才发现浏览器报 `ERR_CERT_COMMON_NAME_INVALID`
- **k8s-resource-limits**：集群 OOM 频发但查不出是谁在吃内存，根因常是某个 Deployment 没设 `limits.memory`

### 方案选择
- **新增 `nginx-ssl-mismatch`**：反向扫描 nginx 配置，逐个 server 块校验 server_name 是否被 `ssl_certificate` 覆盖，并验证证书与私钥 modulus 是否成对
- **新增 `k8s-resource-limits`**：扫描 Deployment/StatefulSet/DaemonSet/Job/CronJob 的容器 resources 配置，识别 5 类问题（无 resources / 只 requests 无 limits / 缺 limits.memory / 缺 requests / limits < requests）
- **技术复用**：`nginx-ssl-mismatch` 复用 `ssl_audit._extract_cert_sans` 和 `_domain_match`，不重复写证书解析
- **版本**：1.0.0 → 1.1.0

### 最终效果
- 审计类型从 6 种 → 8 种
- `nginx_audit.py`：新增 `audit_nginx_ssl_mismatch` + `_cert_key_match`，`_parse_nginx_conf` 扩展解析 `ssl_certificate`/`ssl_certificate_key`
- `k8s_audit.py`：新增 `audit_k8s_resource_limits` + `_parse_quantity` + `_iter_containers`，`_load_yaml_documents` 扩展支持工作负载类型
- `config_audit.py`：注册两个新 audit type，新增 `--workload` 参数
- 报告表格新增「位置」列（便于定位到具体 Deployment/容器）
- `references/check_templates.md` 补两个新审计项详解

### 关键决策
1. **nginx-ssl-mismatch 是反向扫描，与 ssl-cert-match 互补**：后者回答「这些域名有没有证书」，前者回答「nginx 里配的域名有没有证书覆盖」。前者更贴合真实排障路径。
2. **证书私钥成对校验很关键**：证书和私钥不成对时 nginx 直接启动失败，但报错信息是 `[emerg] SSL_CTX_use_PrivateKey`，很多运维看不出根因。提前审计能省一次故障。
3. **k8s-resource-limits 关注 QoS 而非绝对值**：不判断「128Mi 够不够」，只判断「有没有设」。因为资源够不够是业务属性，有没有设是配置规范问题——后者才能规则化。
4. **limits < requests 单列为高危**：这是非法配置，API Server 可能接受但 Pod 行为异常，排查极难。

### 踩坑记录
| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `_parse_nginx_conf` 只解析 proxy_pass，没解析 ssl_certificate | v1.0 只做 upstream 审计，不需要证书路径 | 扩展 server 块解析，加 `ssl_certificate` / `ssl_certificate_key` |
| 2 | `_load_yaml_documents` 只认 ConfigMap/Secret/Ingress | v1.0 只做配置审计 | 扩展 kind 白名单，加 Deployment/StatefulSet/DaemonSet/Job/CronJob |
| 3 | CronJob 的容器路径比其他工作负载多一层 | CronJob → jobTemplate → spec → template → spec | `_iter_containers` 单独处理 CronJob 分支 |

### 可复用经验
1. **同一个技术能力可以有两个视角**：证书校验正着查（域名→证书）和反着查（nginx 配置→证书）是不同痛点，都值得做成独立审计项。
2. **规则化的边界**：「配置有没有设」可规则化，「设的值合不合理」不可规则化。审计工具只做前者，后者留给 SRE 判断。

### 待观察
- 8 种审计类型是否让 `--list-types` 变得复杂（当前输出仍清爽）
- k8s-resource-limits 是否成为 CI 流水线常驻检查（价值可能比单次巡检大）
- 是否值得做 `--all` 参数一次性跑全部适用的审计项
