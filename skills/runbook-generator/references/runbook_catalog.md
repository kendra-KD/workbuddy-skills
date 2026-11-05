# Runbook Catalog · 内置 Runbook 目录详解

> 本文档详细说明每个内置 runbook 的适用场景、根因覆盖范围、排查步骤要点。
> 用于快速判断某个故障应该用哪个 runbook。

---

## 使用方法

```bash
# 查看所有 runbook
python scripts/runbook_matcher.py --list

# 查看单个完整内容
python scripts/runbook_matcher.py --detail <id>

# 关键词匹配
python scripts/runbook_matcher.py <关键词>
```

---

## 目录

### 1. `http-502` · 502 Bad Gateway 排查

**适用**：nginx/ingress 返回 502，后端服务不可达或返回无效响应。

**根因覆盖**：
- 后端服务未启动或已崩溃（🔴 高）
- 后端监听 127.0.0.1 而非 0.0.0.0（🟡 中）
- 后端响应超时被 nginx 切断（🟡 中）
- 后端返回非法 HTTP 响应（🟢 低）

**排查步骤要点**：确认 502 来源 → 检查后端存活 → 检查端口监听 → 直连后端验证 → 检查 upstream 配置 → 看 nginx error.log

**关键命令**：`curl -v`、`kubectl get pods`、`ss -tlnp`、`kubectl port-forward`、`kubectl logs <ingress-controller>`

---

### 2. `http-503` · 503 Service Unavailable 排查

**适用**：服务暂时不可用，通常在滚动更新或实例全部 NotReady 时。

**根因覆盖**：
- 正在滚动更新（🔴 高）
- endpoints 为空（🔴 高）
- 限流/熔断/HPA 缩到 0（🟡 中）
- 资源不足导致健康检查失败（🟡 中）

**排查步骤要点**：确认是否滚动更新 → 检查 endpoints → 检查健康检查配置 → 检查资源 → 检查 HPA

**关键命令**：`kubectl rollout status`、`kubectl get endpoints`、`kubectl describe deployment`、`kubectl top pods`、`kubectl get hpa`

---

### 3. `http-504` · 504 Gateway Timeout 排查

**适用**：网关等待后端响应超时。

**根因覆盖**：
- 后端处理慢（🔴 高）
- 网关超时配置过短（🟡 中）
- 后端 CPU 打满（🟡 中）
- 数据库连接池耗尽（🟡 中）

**排查步骤要点**：确认偶发还是必现 → 看后端慢请求日志 → 检查网关超时配置 → 检查 CPU → 检查数据库连接池

**关键命令**：`curl -w '%{time_total}'`、`kubectl logs`、`kubectl describe ingress`、`kubectl top pods`、`SHOW PROCESSLIST`

---

### 4. `timeout` · 连接超时排查

**适用**：客户端连接目标超时，网络层问题。

**根因覆盖**：
- 目标端口未开放（🔴 高）
- 防火墙/安全组/网络策略拦截（🔴 高）
- DNS 解析错误（🟡 中）
- TCP 握手队列满（🟢 低）

**排查步骤要点**：确认端口可达 → 检查 DNS → traceroute → 检查防火墙 → 确认目标监听

**关键命令**：`telnet`、`tcping`、`nslookup`、`dig`、`traceroute`、`mtr`、`iptables -L`

---

### 5. `connection-refused` · Connection Refused 排查

**适用**：连接被明确拒绝（端口无服务监听）。

**根因覆盖**：
- 服务未启动（🔴 高）
- 监听 127.0.0.1（🔴 高）
- 端口不一致（🟡 中）
- 服务刚启动未完成监听（🟢 低）

**排查步骤要点**：确认进程存活 → 确认监听地址端口 → telnet 验证 → 看启动日志

**关键命令**：`kubectl get pods`、`ps aux`、`ss -tlnp`、`telnet`、`kubectl logs`

---

### 6. `cert-expiry` · SSL/TLS 证书过期排查与更新

**适用**：证书过期或即将过期，需更新证书。

**根因覆盖**：
- 证书已过期（🔴 高）
- 即将过期需提前更新（🔴 高）
- 更新了证书但 secret 未同步（🟡 中）
- 更新了 secret 但未 reload（🟡 中）

**排查步骤要点**：确认有效期 → 申请新证书 → 更新 K8s secret → 触发 ingress reload → 同步 CDN → 验证

**关键命令**：`openssl s_client`、`openssl x509 -dates`、`kubectl create secret tls`、`kubectl rollout restart`、`kubectl delete pod -l`

> 💡 配合 `ssl-cert-monitor` Skill 做批量证书到期检查，提前发现提前处理。

---

### 7. `pod-crashloopbackoff` · Pod CrashLoopBackOff 排查

**适用**：Pod 反复崩溃重启。

**根因覆盖**：
- 应用启动报错（🔴 高）
- command/args 配置错误（🟡 中）
- OOMKilled（🟡 中）
- 健康检查过严（🟡 中）
- 镜像问题（🟢 低）

**排查步骤要点**：看 pod 状态 → 当前日志 → **--previous 日志（关键）** → describe 看 Last State → OOM 则查内存 → 临时 sleep 存活排查

**关键命令**：`kubectl get pod`、`kubectl logs`、`kubectl logs --previous`、`kubectl describe pod`、`kubectl top pod`

**退出码速查**：
- Exit 137 = OOMKilled
- Exit 1 = 应用报错
- Exit 0 但重启 = 健康检查失败

---

### 8. `minio-s3-500` · MinIO/S3 返回 500 排查

**适用**：MinIO 或 S3 兼容存储返回 500，预签名 URL 失败。

**根因覆盖**：
- vhost vs path-style 不一致（🔴 高）
- 预签名 URL Host header 被改写（🔴 高）
- bucket 不存在或权限不足（🟡 中）
- MinIO 版本 bug 或磁盘故障（🟢 低）

**排查步骤要点**：看错误响应体 → 看 MinIO 日志 → 确认 SDK 访问模式 → 检查 nginx Host header → mc 直连测试 → 统一入口方案

**关键命令**：`curl -v`、`kubectl logs <minio>`、`mc alias set`、`mc ls`、`mc cp`、`cat nginx.conf`

**架构级解决方案**：用 minio-nginx 统一对外入口，`proxy_set_header Host $http_host;` 保留原始 Host。

---

### 9. `disk-full` · 磁盘空间满排查

**适用**：磁盘空间不足导致服务异常。

**根因覆盖**：
- 日志未轮转清理（🔴 高）
- 容器日志撑满节点（🔴 高）
- 业务数据堆积（🟡 中）
- coredump 堆积（🟢 低）

**排查步骤要点**：df -h 定位 → du 找大文件 → 清理容器日志 → 清理 pod 日志 → 清理系统临时文件 → 归档业务数据

**关键命令**：`df -h`、`find -size +500M`、`du -sh`、`truncate`、`journalctl --vacuum-size`、`find -mtime +7 -delete`

**安全清理原则**：truncate 不删运行中容器日志；业务数据先归档再删；7 天前日志才清理。

---

### 10. `oom-killed` · OOM Killed 排查

**适用**：进程/pod 因内存超限被 kill。

**根因覆盖**：
- 内存泄漏（🔴 高）
- limit 设置过低（🔴 高）
- 单次处理大内存数据（🟡 中）
- 并发太高导致内存峰值（🟡 中）

**排查步骤要点**：确认 OOMKilled → 看 limit/request → 看内存趋势 → 看 OOM 前日志 → Java 查 JVM 配置 → 抓 heap dump

**关键命令**：`kubectl describe pod`、`kubectl top pod`、`kubectl logs --previous`、`jps -v`、`jmap -dump`、`kubectl cp`

**Java 特别注意**：-Xmx 应小于 pod memory limit 的 75%，留空间给非堆内存。

---

### 11. `dns-resolution-failure` · DNS 解析失败排查

**适用**：域名无法解析或解析到错误 IP，服务访问失败。

**根因覆盖**：
- DNS 服务器不可达或故障（🔴 高）
- 域名未注册/已过期/DNS 记录未生效（🔴 高）
- K8s CoreDNS 异常（🟡 中）
- 本地 /etc/resolv.conf 配置错误（🟡 中）
- DNS 缓存了错误结果（🟢 低）

**排查步骤要点**：确认是否 DNS 问题 → 查本地 DNS 配置 → 查域名注册和 DNS 记录 → K8s 查 CoreDNS → 查 DNS 服务商控制台 → 清 DNS 缓存重试

**关键命令**：`nslookup`、`dig`、`whois`、`kubectl get pod -n kube-system | grep coredns`、`cat /etc/resolv.conf`

**与 timeout 的区别**：timeout 是网络层超时（连不上 IP），DNS 失败是连 IP 都没拿到（解析阶段就挂了）。

---

### 12. `db-connection-failure` · 数据库连接失败排查

**适用**：应用无法连接 MySQL/PostgreSQL/Redis，连接失败或超时。

**根因覆盖**：
- 数据库服务未启动或崩溃（🔴 高）
- 网络不通（防火墙/安全组/网络策略）（🔴 高）
- 凭据错误（🔴 高）
- 连接池耗尽（🟡 中）
- 数据库只允许特定 IP 连接（🟡 中）

**排查步骤要点**：确认数据库存活 → 测试端口连通性 → 命令行客户端相同凭据测试 → 查连接数和 max_connections → 查访问控制配置 → 查应用侧配置

**关键命令**：`mysql -h ... -u ... -p`、`psql -h ... -U ...`、`redis-cli -h ... -a ...`、`SHOW PROCESSLIST`、`SHOW VARIABLES LIKE 'max_connections'`、`grep bind-address`

**与 connection-refused 的区别**：connection-refused 是端口明确拒绝（网络层），db-connection-failure 是数据库层面的全面排查（含凭据/连接池/权限/配置）。

---

### 13. `pod-pending` · K8s Pod Pending 排查

**适用**：Pod 一直 Pending 无法调度，kubectl describe 显示 FailedScheduling。

**根因覆盖**：
- 节点 CPU/内存资源不足（🔴 高）
- 节点有污点且 pod 未配 toleration（🔴 高）
- PVC 绑定失败（🟡 中）
- 节点 NotReady（🟡 中）
- nodeSelector 标签不匹配（🟢 低）

**排查步骤要点**：describe pod 看 Events → 查节点资源水位 → 查节点污点和 toleration → 查 PVC 状态 → 查节点 NotReady → 查 nodeSelector 标签

**关键命令**：`kubectl describe pod`、`kubectl top nodes`、`kubectl get nodes -o custom-columns=...,TAINTS:...`、`kubectl get pvc`、`kubectl get nodes -o wide`

**与 pod-crashloopbackoff 的区别**：Pending 是还没调度上去（没运行过），CrashLoopBackOff 是调度上去了但反复崩溃重启。

---

### 14. `docker-container-start-failure` · Docker 容器无法启动排查

**适用**：Docker 容器启动后立即退出（Exited）或无法创建。

**根因覆盖**：
- 容器启动后进程立即退出（🔴 高）
- 端口冲突（🔴 高）
- 镜像问题（🟡 中）
- 挂载路径不存在或权限不足（🟡 中）
- entrypoint/command 配置错误（🟡 中）

**排查步骤要点**：确认退出码 → docker logs → 查端口冲突 → 查镜像和架构 → 查挂载路径和权限 → 交互模式进入容器手动排查

**关键命令**：`docker ps -a`、`docker inspect --format='{{.State.ExitCode}}'`、`docker logs`、`ss -tlnp`、`docker pull`、`docker run -it --entrypoint /bin/sh`

**退出码速查**：0=正常退出（无前台进程）；127=命令找不到；126=权限不足；137=OOM；1=应用报错。

---

### 15. `nginx-config-error` · Nginx 配置语法错误排查

**适用**：nginx -t 失败或 reload 后服务异常，配置文件语法错误。

**根因覆盖**：
- 配置行缺少分号或括号不匹配（🔴 高）
- proxy_pass 指向的 upstream/service 不存在（🔴 高）
- include 的子配置文件有语法错误（🟡 中）
- 变量未定义或拼写错误（🟡 中）
- SSL 证书路径错误或文件不存在（🟢 低）

**排查步骤要点**：nginx -t 定位错误行 → 查报错行附近配置 → 查 proxy_pass 和 upstream → 查 include 子配置 → 查 SSL 证书配置 → 备份后 reload

**关键命令**：`nginx -t`、`grep -rn 'proxy_pass' /etc/nginx/`、`grep -rn 'upstream' /etc/nginx/ -A5`、`openssl x509 -noout -modulus | md5sum`、`nginx -s reload`

**安全提醒**：reload 前必须 nginx -t 测试通过，且备份当前可用配置；reload 后异常立即回滚备份。

---

### 16. `k8s-node-notready` · K8s 节点 NotReady 排查

**适用**：K8s 节点状态变为 NotReady，该节点上的 pod 无法被访问或新 pod 无法调度。

**根因覆盖**：
- kubelet 进程异常或证书过期（🔴 高）
- 网络插件（flannel/calico/cilium）异常（🔴 高）
- 节点磁盘满导致 kubelet 无法写入（🟡 中）
- 节点内存或 CPU 压力过大（🟡 中）
- API Server 与节点网络不可达（🟢 低）

**排查步骤要点**：`kubectl get nodes` 确认状态 → `systemctl status kubelet` + `journalctl -u kubelet` → 检查 CNI pod 状态 → 检查节点资源（df/free/top） → 测试节点到 API Server 6443 连通性

**关键命令**：`kubectl get nodes -o wide`、`systemctl status kubelet`、`journalctl -u kubelet -n 200`、`kubectl get pod -n kube-system | grep -E 'flannel|calico|cilium'`、`df -h`、`free -m`、`curl -k https://<apiserver>:6443/healthz`

---

### 17. `mysql-slow-query` · MySQL 慢查询排查

**适用**：MySQL 查询响应慢，业务反馈数据库卡慢。

**根因覆盖**：
- 缺少合适索引或索引未生效（🔴 高）
- SQL 写法导致全表扫描（🔴 高）
- 表数据量过大且未分区/归档（🟡 中）
- 锁等待或死锁（ 中）
- 服务器 IO/CPU/内存瓶颈（🟢 低）

**排查步骤要点**：确认慢查询日志或 performance_schema → `EXPLAIN` 分析执行计划 → 检查表索引和统计信息 → 检查锁等待和并发情况 → 监控服务器资源

**关键命令**：`tail -n 100 /var/lib/mysql/slow.log`、`EXPLAIN <慢 SQL>`、`SHOW INDEX FROM <表名>`、`SHOW ENGINE INNODB STATUS`、`SHOW PROCESSLIST`、`iostat -x 1 5`

---

### 18. `redis-memory-full` · Redis 内存满/OOM 排查

**适用**：Redis 内存使用达到上限，写入失败、驱逐异常或 OOM。

**根因覆盖**：
- maxmemory 设置过低（🔴 高）
- 缓存数据未设置过期时间（ 高）
- 存在大 key 或热 key（🟡 中）
- 淘汰策略为 noeviction（🟡 中）
- 客户端连接/管道使用不当（🟢 低）

**排查步骤要点**：`redis-cli INFO memory` 确认内存使用 → 检查 `maxmemory` 和 `maxmemory-policy` → `redis-cli --bigkeys` 找大 key → 抽样检查 key TTL → 清理或扩容

**关键命令**：`redis-cli INFO memory`、`redis-cli CONFIG GET maxmemory`、`redis-cli --bigkeys`、`redis-cli --scan --pattern '*'`、`redis-cli CONFIG SET maxmemory-policy allkeys-lru`

---

### 19. `ingress-not-working` · K8s Ingress 访问不通排查

**适用**：通过 Ingress 访问服务失败，包括 502/503/域名访问不到/HTTPS 证书错误。

**根因覆盖**：
- Ingress Controller pod 异常（🔴 高）
- Ingress 的 host/path 规则配置错误（ 高）
- 后端 service/pod 异常（🔴 高）
- SSL 证书配置错误（🟡 中）
- DNS 解析错误或本地 hosts 未配置（🟡 中）

**排查步骤要点**：检查 Ingress Controller pod 状态和日志 → `kubectl describe ingress` 确认 host/path/backend → 检查后端 service/endpoints/pod → 检查 TLS secret → 从集群内直接测试后端 service

**关键命令**：`kubectl get pod -n <ic-ns>`、`kubectl describe ingress <名> -n <ns>`、`kubectl get endpoints <svc>`、`kubectl get secret <tls-secret>`、`kubectl exec -it <pod> -- curl http://<svc>:<port>`

---

### 20. `jenkins-build-failure` · Jenkins 构建失败排查

**适用**：Jenkins 构建/流水线失败，包括编译失败、依赖下载失败、环境配置错误、权限不足、节点资源不足。

**根因覆盖**：
- 代码编译/测试失败（🔴 高）
- 依赖下载失败（网络/私服/版本不存在）（🔴 高）
- Jenkins agent 节点环境缺失（🟡 中）
- 权限不足（无法拉取代码/推送镜像）（🟡 中）
- 节点磁盘/内存/CPU 不足（🟢 低）

**排查步骤要点**：查看 Console Output 定位错误 → 检查依赖/包下载是否成功 → 检查 Jenkins 节点环境和工具版本 → 检查凭据和权限 → 检查节点资源

**关键命令**：`curl -u <user>:<token> '<jenkins>/job/<job>/<build>/consoleText'`、`which java mvn node npm docker git`、`git clone <repo>`、`docker login <registry>`、`df -h`、`free -m`、`nproc`

---

### 21. `docker-image-pull-failure` · Docker 镜像拉取失败排查

**适用**：K8s pod 或 Docker 拉取镜像失败，出现 ImagePullBackOff/ErrImagePull。

**根因覆盖**：
- 镜像不存在或 tag 错误（🔴 高）
- 镜像仓库需认证（无权限/secret 错误）（🔴 高）
- 网络不通或 DNS 解析失败（🟡 中）
- 镜像架构不匹配（如 arm64 节点拉 amd64 镜像）（🟡 中）
- 镜像仓库限流或故障（🟢 低）

**排查步骤要点**：`kubectl describe pod` 查看 Events → 确认镜像名和 tag 正确 → 手动 `docker pull` 验证 → 检查 imagePullSecrets 和认证 → 检查节点网络到仓库 → 确认镜像架构

**关键命令**：`kubectl describe pod <pod> -n <ns>`、`docker pull <镜像>:<tag>`、`docker login <registry>`、`kubectl get secret <pull-secret> -n <ns>`、`crane manifest <镜像>:<tag>` 或 `docker manifest inspect`

---

### 22. `high-cpu-usage` · CPU 使用率过高排查

**适用**：服务器或容器 CPU 使用率持续高位，业务响应变慢。

**根因覆盖**：
- 某进程死循环或计算密集型任务（🔴 高）
- 并发量突增（🟡 中）
- 定时任务/批处理集中执行（🟡 中）
- 应用代码性能问题（如低效 SQL/算法）（🟢 低）
- 系统资源本身不足（🟢 低）

**排查步骤要点**：`top`/`htop` 找高 CPU 进程 → 找线程（`top -H` / `ps -eL`） → 抓堆栈/火焰图 → 分析代码或 SQL → 限制或扩容

**关键命令**：`top -bn1 -o %CPU`、`ps -eLo pid,tid,comm,%cpu --sort=-%cpu | head -20`、`top -H -p <pid>`、`jstack <pid>` 或 `perf top`、`pidstat -u 1 5`

---

### 23. `log-disk-full` · 日志目录磁盘满排查

**适用**：`/var/log` 等日志目录磁盘满，影响服务写入和系统稳定。

**根因覆盖**：
- 日志未轮转或轮转周期过长（ 高）
- 应用日志级别过低/量过大（🔴 高）
- 某个进程持续写超大日志（🟡 中）
- 日志清理脚本失效（🟡 中）
- 磁盘容量本身过小（🟢 低）

**排查步骤要点**：`df -h` 确认哪个目录满 → `du -sh /var/log/*` 定位大日志 → 检查 logrotate 配置 → 清理/压缩过期日志 → 调整日志级别/轮转策略 → 监控防止复发

**关键命令**：`df -h`、`du -sh /var/log/*`、`ls -lhS /var/log/ | head -20`、`lsof +L1 /var/log`（找已删除但仍被占用的文件）、`logrotate -d /etc/logrotate.conf`、`journalctl --vacuum-time=7d`
