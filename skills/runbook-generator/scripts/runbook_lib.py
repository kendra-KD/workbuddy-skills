#!/usr/bin/env python3
"""
Runbook Library — 10 个内置运维故障 runbook 数据库。
每个 runbook 含：故障概述、根因假设树、排查步骤、验证方法、回退方案。

纯数据模块，不含执行逻辑。被 runbook_matcher.py 导入使用。
也可独立查看：python runbook_lib.py --list
"""

import argparse
import json
import sys

# ============================================================
# 内置 Runbook 数据库
# 每条 runbook 结构：
#   id, title, keywords[], summary, root_causes[], steps[], verify, rollback
# step 结构：action, command, expected, judgment
# ============================================================

RUNBOOKS = [
    # ─────────────── 1. HTTP 502 ───────────────
    {
        "id": "http-502",
        "title": "502 Bad Gateway 排查",
        "keywords": ["502", "bad gateway", "网关错误", "502 bad gateway", "badgateway"],
        "summary": "上游服务返回无效响应，通常是后端服务不可达、崩溃或响应格式错误。常见于 nginx/ingress 转发到后端服务时后端未正常响应。",
        "root_causes": [
            {"cause": "后端服务未启动或已崩溃", "verify": "检查后端服务进程/pod 状态", "probability": "高"},
            {"cause": "后端服务端口监听错误（监听了 127.0.0.1 而非 0.0.0.0）", "verify": "ss -tlnp | grep <端口>", "probability": "中"},
            {"cause": "后端服务响应超时被 nginx 切断", "verify": "检查 nginx error.log 中的 upstream timeout", "probability": "中"},
            {"cause": "后端服务返回了非法 HTTP 响应（如直接返回裸 JSON 无 HTTP 头）", "verify": "curl -v 直接请求后端端口", "probability": "低"},
        ],
        "steps": [
            {
                "action": "确认 502 来源——是 nginx/ingress 还是后端直接返回",
                "command": "curl -v http://<域名或IP>",
                "expected": "响应头里看 Server 字段，以及响应体是否含 nginx/ingress 标识",
                "judgment": "如果是 nginx 返回的 502，说明 nginx 转发后端失败；如果是后端自身返回，说明后端代码有问题",
            },
            {
                "action": "检查后端服务是否存活",
                "command": "# K8s 环境\nkubectl get pods -n <namespace> | grep <服务名>\n# 非 K8s 环境\nps aux | grep <服务进程名>",
                "expected": "pod 处于 Running 状态且 READY 列正常；进程存在",
                "judgment": "如果 pod 不在 Running 或进程不存在，说明后端挂了，先重启服务",
            },
            {
                "action": "检查后端服务端口监听情况",
                "command": "# 在后端服务所在机器/pod 上执行\nss -tlnp | grep <后端端口>\n# 或\nnetstat -tlnp | grep <后端端口>",
                "expected": "端口监听在 0.0.0.0:<端口> 而非 127.0.0.1:<端口>",
                "judgment": "如果监听在 127.0.0.1，外部/nginx 无法连接，需改监听地址为 0.0.0.0",
            },
            {
                "action": "直接请求后端端口绕过 nginx 验证",
                "command": "# K8s：先 port-forward\nkubectl port-forward svc/<服务名> <本地端口>:<服务端口> -n <namespace>\n# 然后\ncurl -v http://127.0.0.1:<本地端口>/api/health",
                "expected": "后端直接请求返回 200 或正常业务响应",
                "judgment": "如果后端直连正常但经 nginx 502，问题在 nginx 配置或网络策略；如果后端直连也异常，问题在后端本身",
            },
            {
                "action": "检查 nginx/ingress 配置中的 upstream 指向",
                "command": "# ingress\nkubectl describe ingress <ingress名> -n <namespace>\n# nginx 配置\ncat /etc/nginx/conf.d/<配置文件>.conf | grep -A5 upstream",
                "expected": "upstream 指向的 service/port 正确",
                "judgment": "如果 upstream service 名写错或端口写错，修正配置",
            },
            {
                "action": "查看 nginx error.log 定位具体上游错误",
                "command": "# ingress controller 日志\nkubectl logs -n kube-system <ingress-controller-pod> --tail=50 | grep <域名>\n# nginx 本机\ntail -50 /var/log/nginx/error.log",
                "expected": "看到具体的 upstream 错误（connect refused / timeout / invalid response）",
                "judgment": "根据具体错误对应到根因：refused→后端没起；timeout→后端慢或网络不通；invalid→后端返回非法响应",
            },
        ],
        "verify": "curl -I http://<域名> 返回 200 或预期业务状态码，且连续 3 次稳定。",
        "rollback": "如果排查过程中改了 nginx 配置导致更严重，回滚配置：\n# K8s ingress\nkubectl rollout undo deployment/<ingress-controller> -n kube-system\n# nginx 本机\ncp /etc/nginx/conf.d/<配置>.conf.bak /etc/nginx/conf.d/<配置>.conf && nginx -s reload",
    },
    # ─────────────── 2. HTTP 503 ───────────────
    {
        "id": "http-503",
        "title": "503 Service Unavailable 排查",
        "keywords": ["503", "service unavailable", "服务不可用", "503 service", "unavailable"],
        "summary": "服务暂时不可用，通常是后端服务过载、正在重启、或负载均衡后端实例全部不可用。与 502 的区别：503 是服务知道自己暂时不可用，502 是网关收到无效响应。",
        "root_causes": [
            {"cause": "后端服务正在重启/滚动更新中", "verify": "kubectl rollout status deployment/<服务>", "probability": "高"},
            {"cause": "后端实例全部 NotReady 或被踢出负载均衡", "verify": "kubectl get endpoints <service>", "probability": "高"},
            {"cause": "服务限流/熔断触发（如 HPA 缩到 0 或限流配置过严）", "verify": "检查 HPA 和限流配置", "probability": "中"},
            {"cause": "后端实例资源不足（CPU/内存）导致健康检查失败", "verify": "kubectl describe pod 查看 events", "probability": "中"},
        ],
        "steps": [
            {
                "action": "确认是否正在滚动更新",
                "command": "kubectl rollout status deployment/<服务名> -n <namespace>",
                "expected": "deployment successfully rolled out 或显示进度",
                "judgment": "如果正在更新中，等待更新完成即可；如果卡住，检查新版本 pod 是否健康",
            },
            {
                "action": "检查 service 的 endpoints 是否为空",
                "command": "kubectl get endpoints <service名> -n <namespace>",
                "expected": "ENDPOINTS 列有 IP:端口 列表",
                "judgment": "如果 ENDPOINTS 是 <none>，说明没有 pod 通过健康检查，需要排查 pod 健康状态",
            },
            {
                "action": "检查 pod 健康检查配置",
                "command": "kubectl describe deployment <服务名> -n <namespace> | grep -A10 -i 'liveness\\|readiness'",
                "expected": "livenessProbe/readinessProbe 配置合理（路径、端口、超时）",
                "judgment": "如果健康检查路径返回非 200，pod 会被标记不健康；如果检查超时太短，高峰期会误判",
            },
            {
                "action": "检查 pod 资源使用是否到上限",
                "command": "kubectl top pods -n <namespace> | grep <服务名>\n# 或\nkubectl describe pod <pod名> -n <namespace> | grep -A5 -i 'limits\\|requests'",
                "expected": "CPU/内存使用未达 limits 上限",
                "judgment": "如果接近 limits，考虑扩容或调大资源限制",
            },
            {
                "action": "查看 HPA 是否缩容到 0",
                "command": "kubectl get hpa -n <namespace> | grep <服务名>",
                "expected": "REPLICAS 显示 >0，TARGETS 未到 min",
                "judgment": "如果 REPLICAS 是 0/0，说明 HPA 因指标异常缩到 0，需检查 metrics-server 或手动扩容",
            },
        ],
        "verify": "kubectl get endpoints <service> 有 IP 列表，且 curl http://<域名> 返回 200。",
        "rollback": "如果是滚动更新导致且需立即恢复：\nkubectl rollout undo deployment/<服务名> -n <namespace>\n如果是 HPA 缩到 0：\nkubectl scale deployment/<服务名> --replicas=<最小实例数> -n <namespace>",
    },
    # ─────────────── 3. HTTP 504 ───────────────
    {
        "id": "http-504",
        "title": "504 Gateway Timeout 排查",
        "keywords": ["504", "gateway timeout", "网关超时", "timeout", "网关超时"],
        "summary": "网关在等待后端响应时超时。后端服务处理太慢，超过了网关（nginx/ingress）配置的超时时间。",
        "root_causes": [
            {"cause": "后端处理逻辑慢（数据库慢查询、外部 API 调用超时、死循环）", "verify": "查看后端应用日志和 APM 链路追踪", "probability": "高"},
            {"cause": "网关超时配置过短（nginx proxy_read_timeout 太小）", "verify": "检查 nginx/ingress 超时配置", "probability": "中"},
            {"cause": "后端资源不足（CPU 打满导致处理排队）", "verify": "kubectl top pods 查 CPU 使用", "probability": "中"},
            {"cause": "数据库连接池耗尽，请求排队等连接", "verify": "查看数据库连接池监控和 max_connections", "probability": "中"},
        ],
        "steps": [
            {
                "action": "确认是偶发还是必现 504",
                "command": "for i in $(seq 1 10); do curl -o /dev/null -s -w '%{http_code} %{time_total}s\\n' http://<域名>/api/<接口>; done",
                "expected": "看返回码分布和响应时间分布",
                "judgment": "偶发 504 + 高延迟→后端间歇性慢；必现 504→后端卡死或超时配置问题",
            },
            {
                "action": "查看后端应用日志，定位慢请求",
                "command": "kubectl logs -f deployment/<服务名> -n <namespace> --tail=100 | grep -i 'slow\\|timeout\\|elapsed'",
                "expected": "看到慢请求记录或超时日志",
                "judgment": "如果后端日志显示某个 DB 查询耗时长，排查数据库；如果显示外部 API 调用超时，排查下游服务",
            },
            {
                "action": "检查 nginx/ingress 超时配置",
                "command": "# ingress annotation\nkubectl describe ingress <ingress名> -n <namespace> | grep -i timeout\n# nginx 配置\ngrep -r 'proxy_read_timeout\\|proxy_connect_timeout' /etc/nginx/",
                "expected": "proxy_read_timeout 默认 60s，长接口应调大",
                "judgment": "如果接口正常需要 90s 但网关配 60s，调大超时（ingress 加 annotation: nginx.ingress.kubernetes.io/proxy-read-timeout: '120'）",
            },
            {
                "action": "检查后端 CPU/内存是否打满",
                "command": "kubectl top pods -n <namespace> | grep <服务名>",
                "expected": "CPU% 未接近 100%（limit 值）",
                "judgment": "如果 CPU 打满，扩容副本数或排查是否有死循环",
            },
            {
                "action": "检查数据库连接池状态",
                "command": "# MySQL\nSHOW PROCESSLIST;\nSHOW VARIABLES LIKE 'max_connections';\n# 应用侧连接池监控（如 HikariCP）\nkubectl logs deployment/<服务名> -n <namespace> | grep -i 'connection\\|pool'",
                "expected": "活跃连接数远低于 max_connections",
                "judgment": "如果连接数接近上限，排查是否有连接泄漏（未关闭的连接）或调大连接池",
            },
        ],
        "verify": "连续调用接口 10 次，响应时间在预期范围内，无 504。",
        "rollback": "如果调大了网关超时但后端仍慢，先回滚超时配置避免掩盖真实问题：\n# 移除 ingress 的 timeout annotation\nkubectl annotate ingress <名> nginx.ingress.kubernetes.io/proxy-read-timeout- -n <namespace>",
    },
    # ─────────────── 4. 超时 ───────────────
    {
        "id": "timeout",
        "title": "连接超时排查",
        "keywords": ["timeout", "超时", "connection timed out", "timed out", "连接超时"],
        "summary": "客户端连接目标服务时超时，未建立连接或未收到响应。可能是网络不通、防火墙拦截、目标端口未开放、DNS 解析异常。",
        "root_causes": [
            {"cause": "目标服务端口未开放或服务未启动", "verify": "telnet/tcping 目标端口", "probability": "高"},
            {"cause": "网络不通（防火墙/安全组/网络策略拦截）", "verify": "traceroute + 安全组规则检查", "probability": "高"},
            {"cause": "DNS 解析到了错误 IP 或解析超时", "verify": "nslookup/dig 检查解析结果", "probability": "中"},
            {"cause": "目标服务负载过高，TCP 握手队列满", "verify": "ss -s 查看 TCP 连接统计", "probability": "低"},
        ],
        "steps": [
            {
                "action": "确认目标 IP 和端口是否可达",
                "command": "# 测试 TCP 端口连通性\ntelnet <目标IP> <端口>\n# 或\ntcping <目标IP> <端口>\n# 或\nnc -zv <目标IP> <端口> -w 5",
                "expected": "Connected 或 succeeded",
                "judgment": "如果不通，排查网络/安全组/服务是否启动",
            },
            {
                "action": "检查 DNS 解析是否正确",
                "command": "nslookup <域名>\n# 或\ndig <域名> +short",
                "expected": "解析到的 IP 是预期目标 IP",
                "judgment": "如果解析到错误 IP，检查 DNS 配置（/etc/resolv.conf 或 CoreDNS）；如果解析超时，排查 DNS 服务可达性",
            },
            {
                "action": " traceroute 排查网络路径",
                "command": "traceroute <目标IP>\n# 或\nmtr <目标IP> --report",
                "expected": "每一跳都正常响应，最终到达目标",
                "judgment": "如果某一跳开始丢包或超时，定位网络断点在哪一跳",
            },
            {
                "action": "检查防火墙/安全组/网络策略",
                "command": "# K8s 网络策略\nkubectl get networkpolicy -n <namespace> -o yaml | grep -A5 <服务名>\n# 云服务器安全组：登录云控制台查看入站规则\n# 本机 iptables\niptables -L -n | grep <端口>",
                "expected": "目标端口在放行规则中",
                "judgment": "如果安全组/网络策略未放行目标端口，添加放行规则",
            },
            {
                "action": "在目标服务侧确认端口监听状态",
                "command": "# 在目标机器执行\nss -tlnp | grep <端口>",
                "expected": "端口在监听且监听在 0.0.0.0",
                "judgment": "如果端口未监听，启动服务；如果监听在 127.0.0.1，改为 0.0.0.0",
            },
        ],
        "verify": "telnet <目标IP> <端口> 成功，且 curl http://<域名> 正常响应。",
        "rollback": "网络排查通常无副作用。如果修改了 iptables 规则导致新问题：\niptables -D <规则>  # 删除新加的规则",
    },
    # ─────────────── 5. Connection Refused ───────────────
    {
        "id": "connection-refused",
        "title": "Connection Refused 排查",
        "keywords": ["connection refused", "连接拒绝", "econnrefused", "refused", "连接被拒"],
        "summary": "目标端口主动拒绝连接（收到 RST 包），说明目标 IP 可达但端口上没有服务监听。与 timeout 的区别：refused 是明确拒绝，timeout 是没人响应。",
        "root_causes": [
            {"cause": "目标服务未启动或已崩溃", "verify": "检查服务进程/pod 状态", "probability": "高"},
            {"cause": "服务监听在 127.0.0.1 而非 0.0.0.0", "verify": "ss -tlnp 看监听地址", "probability": "高"},
            {"cause": "服务监听端口跟客户端连接端口不一致", "verify": "确认服务实际监听端口", "probability": "中"},
            {"cause": "服务刚启动还未完成端口监听（启动慢）", "verify": "等待几秒后重试", "probability": "低"},
        ],
        "steps": [
            {
                "action": "确认目标服务进程是否存活",
                "command": "# K8s\nkubectl get pods -n <namespace> | grep <服务名>\n# 非 K8s\nps aux | grep <服务进程名>",
                "expected": "pod Running 且 READY 正常；进程存在",
                "judgment": "如果服务未运行，先启动服务",
            },
            {
                "action": "确认端口监听地址和端口",
                "command": "# 在服务所在机器/pod 执行\nss -tlnp | grep <服务名或端口>",
                "expected": "0.0.0.0:<端口> 或 [::]:<端口>",
                "judgment": "如果是 127.0.0.1:<端口>，外部连接会 refused，需改监听地址；如果端口跟预期不符，确认实际监听端口",
            },
            {
                "action": "从客户端直接 telnet 验证",
                "command": "telnet <目标IP> <端口>",
                "expected": "Connected（如果服务正常）或 Connection refused（如果端口确实没监听）",
                "judgment": "refused 确认是端口无服务监听，回到步骤 2 修正监听配置",
            },
            {
                "action": "检查服务启动日志是否有异常",
                "command": "kubectl logs <pod名> -n <namespace> --tail=50\n# 或\njournalctl -u <服务名> --no-pager -n 50",
                "expected": "无 ERROR/FATAL 日志，服务正常启动",
                "judgment": "如果有启动报错（如端口冲突、配置错误），修复后重启服务",
            },
        ],
        "verify": "telnet <目标IP> <端口> 返回 Connected，curl 正常响应。",
        "rollback": "无副作用。如果修改了服务监听地址，重启服务即可生效，无需回滚。",
    },
    # ─────────────── 6. 证书过期 ───────────────
    {
        "id": "cert-expiry",
        "title": "SSL/TLS 证书过期排查与更新",
        "keywords": ["证书过期", "cert expired", "ssl error", "证书快过期", "tls", "ssl 证书", "certificate"],
        "summary": "SSL/TLS 证书已过期或即将过期，导致 HTTPS 访问报错。需要更新证书并替换 K8s secret 或 nginx 配置。",
        "root_causes": [
            {"cause": "证书已过期，浏览器/客户端报 NET::ERR_CERT_DATE_INVALID", "verify": "openssl s_client 查看证书有效期", "probability": "高"},
            {"cause": "证书即将过期（7天内），需提前更新避免过期", "verify": "用 ssl-cert-monitor Skill 批量检查", "probability": "高"},
            {"cause": "更新了证书但 K8s secret/nginx 未同步替换", "verify": "对比 secret 内容和证书文件", "probability": "中"},
            {"cause": "更新了 secret 但 pod/ingress 未 reload", "verify": "重启 ingress controller 或 nginx", "probability": "中"},
        ],
        "steps": [
            {
                "action": "确认当前证书有效期",
                "command": "echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -dates",
                "expected": "notBefore 和 notAfter 日期，notAfter 在未来",
                "judgment": "如果 notAfter 已过去，证书已过期；如果在 7 天内，紧急更新",
            },
            {
                "action": "申请新证书（阿里云免费证书 / Let's Encrypt）",
                "command": "# 阿里云：登录控制台 → 数字证书管理 → 免费证书 → 申请\n# Let's Encrypt：\ncertbot certonly --nginx -d <域名>",
                "expected": "下载到证书文件（fullchain.pem + private.key）",
                "judgment": "拿到新证书文件后进入下一步",
            },
            {
                "action": "更新 K8s tls secret",
                "command": "# 删除旧 secret\nkubectl delete secret <tls-secret名> -n <namespace>\n# 创建新 secret\nkubectl create secret tls <tls-secret名> --cert=fullchain.pem --key=private.key -n <namespace>",
                "expected": "secret/<tls-secret名> created",
                "judgment": "secret 更新成功，但 ingress/nginx 需要重新加载才能生效",
            },
            {
                "action": "触发 ingress controller reload",
                "command": "# 强制 ingress controller 重新加载（滚动重启 pod）\nkubectl rollout restart deployment <ingress-controller-deployment> -n kube-system\n# 或删除 pod 触发重建\nkubectl delete pod -l app.kubernetes.io/name=ingress-nginx -n kube-system",
                "expected": "新 pod 启动完成",
                "judgment": "reload 后新证书生效",
            },
            {
                "action": "如果是云 CDN，同步更新 CDN 证书",
                "command": "# 华为云 CDN：控制台 → CDN → 域名管理 → HTTPS配置 → 更新证书\n# 阿里云 CDN：控制台 → CDN → 域名管理 → HTTPS → 更新证书",
                "expected": "CDN 证书更新成功，状态变为已部署",
                "judgment": "CDN 节点生效需 5-10 分钟",
            },
            {
                "action": "验证新证书已生效",
                "command": "echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -dates",
                "expected": "notAfter 更新为新证书的过期日期",
                "judgment": "确认新证书已部署",
            },
        ],
        "verify": "openssl s_client 查看证书 notAfter 已更新，且浏览器访问无证书警告。",
        "rollback": "如果新证书有问题需回滚到旧证书：\n# 保留旧 secret 的 pem/key 内容，重新创建\nkubectl create secret tls <tls-secret名> --cert=<旧fullchain> --key=<旧key> -n <namespace>\n# 再次 reload ingress\nkubectl rollout restart deployment <ingress-controller> -n kube-system",
    },
    # ─────────────── 7. Pod CrashLoopBackOff ───────────────
    {
        "id": "pod-crashloopbackoff",
        "title": "Pod CrashLoopBackOff 排查",
        "keywords": ["crashloopbackoff", "pod crash", "容器重启", "crashloop", "backoff", "pod 重启"],
        "summary": "Pod 反复崩溃重启，K8s 进入 CrashLoopBackOff 状态（指数退避等待重启）。通常是容器内进程启动后立即退出（非 0 退出码）。",
        "root_causes": [
            {"cause": "应用启动报错（配置缺失、依赖服务不可达、数据库连接失败）", "verify": "kubectl logs 查看启动日志", "probability": "高"},
            {"cause": "命令/参数配置错误（command 或 args 写错）", "verify": "kubectl describe pod 看 command", "probability": "中"},
            {"cause": "资源限制太低导致 OOMKilled（被 kill 后重启）", "verify": "kubectl describe pod 看 Last State", "probability": "中"},
            {"cause": "健康检查失败导致 pod 被杀（livenessProbe 配置过严）", "verify": "kubectl describe pod 看 events", "probability": "中"},
            {"cause": "镜像问题（tag 写错、镜像不存在、架构不匹配）", "verify": "kubectl describe pod 看 events 里的拉取错误", "probability": "低"},
        ],
        "steps": [
            {
                "action": "查看 pod 状态和重启次数",
                "command": "kubectl get pod <pod名> -n <namespace> -o wide",
                "expected": "STATUS 列显示 CrashLoopBackOff，RESTARTS 列显示重启次数",
                "judgment": "RESTARTS 高说明反复崩溃，需要看日志定位根因",
            },
            {
                "action": "查看当前容器日志",
                "command": "kubectl logs <pod名> -n <namespace> --tail=50",
                "expected": "应用启动日志，找 ERROR/FATAL/Exception",
                "judgment": "根据错误信息定位：数据库连接失败→检查 DB 可达性；配置缺失→检查 configmap/env；端口冲突→检查端口占用",
            },
            {
                "action": "查看上一次崩溃的日志（关键）",
                "command": "kubectl logs <pod名> -n <namespace> --previous --tail=50",
                "expected": "崩溃前的最后日志，通常含致命错误",
                "judgment": "--previous 查看上次崩溃日志，比当前日志更能定位根因",
            },
            {
                "action": "查看 pod events 和 Last State",
                "command": "kubectl describe pod <pod名> -n <namespace> | grep -A10 -i 'last state\\|state\\|events'",
                "expected": "Last State 含退出码和原因（如 Exit Code 137 = OOMKilled）",
                "judgment": "Exit 137→OOM，需调大 memory limit；Exit 1→应用报错，看日志；Exit 0 但重启→健康检查失败",
            },
            {
                "action": "如果是 OOM，查看内存使用和限制",
                "command": "kubectl describe pod <pod名> -n <namespace> | grep -A5 'Limits\\|Requests'\n# 历史内存使用（需 metrics-server）\nkubectl top pod <pod名> -n <namespace>",
                "expected": "memory limit 和实际使用对比",
                "judgment": "如果实际使用接近 limit，调大 memory limit 或排查内存泄漏",
            },
            {
                "action": "如果配置有问题，临时修改 deployment 验证",
                "command": "# 修改环境变量或配置\nkubectl set env deployment/<deployment名> <KEY>=<VALUE> -n <namespace>\n# 或修改 command\nkubectl patch deployment <deployment名> -n <namespace> --type='json' -p='[{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/command\", \"value\":[\"sh\",\"-c\",\"sleep 3600\"]}]'",
                "expected": "pod 重新部署，用 sleep 保持存活以便进入排查",
                "judgment": "临时用 sleep 让 pod 存活，然后 kubectl exec 进去手动排查",
            },
        ],
        "verify": "kubectl get pod 显示 Running 且 RESTARTS 不再增加，应用日志显示正常启动。",
        "rollback": "如果修改了 deployment 配置导致更严重：\nkubectl rollout undo deployment/<deployment名> -n <namespace>",
    },
    # ─────────────── 8. MinIO/S3 500 ───────────────
    {
        "id": "minio-s3-500",
        "title": "MinIO/S3 返回 500 排查",
        "keywords": ["minio 500", "s3 error", "presigned url", "minio", "s3 500", "internal error", "minio error"],
        "summary": "MinIO 或 S3 兼容存储返回 500 Internal Error，常见于预签名 URL 生成/使用、bucket 策略、vhost vs path-style 访问模式不一致。",
        "root_causes": [
            {"cause": "vhost vs path-style 访问模式不一致（SDK 用 vhost，MinIO 配置 path-style）", "verify": "检查 SDK endpoint 配置和 MinIO 启动参数", "probability": "高"},
            {"cause": "预签名 URL 的 Host header 被代理改写", "verify": "检查 minio-nginx 的 proxy_set_header", "probability": "高"},
            {"cause": "bucket 不存在或权限不足", "verify": "mc ls 或 aws s3 ls 检查 bucket", "probability": "中"},
            {"cause": "MinIO 版本 bug 或磁盘故障", "verify": "查看 MinIO 日志", "probability": "低"},
        ],
        "steps": [
            {
                "action": "查看 MinIO 返回的具体错误响应体",
                "command": "curl -v '<报错的URL或预签名URL>' 2>&1 | grep -A20 '<Error>'",
                "expected": "XML 错误体含 Code 和 Message",
                "judgment": "根据 Code 定位：InternalError→服务端问题；NoSuchBucket→bucket 不存在；AccessDenied→权限问题",
            },
            {
                "action": "检查 MinIO 日志",
                "command": "# K8s\nkubectl logs <minio-pod> -n <namespace> --tail=50 | grep -i 'error\\|panic'\n# 非 K8s\ndocker logs <minio容器> --tail 50 | grep -i 'error\\|panic'",
                "expected": "MinIO 日志中的具体错误堆栈",
                "judgment": "如果是 panic 或 disk error，是 MinIO 本身问题；如果是 routing/path 相关，是访问模式问题",
            },
            {
                "action": "确认 SDK / 客户端的访问模式（vhost vs path-style）",
                "command": "# 检查 SDK 配置（以 boto3 为例）\nimport boto3\ns3 = boto3.client('s3', endpoint_url='http://<minio>', aws_access_key_id='<k>', aws_secret_access_key='<s>')\n# 关键：path-style 必须开启\ns3.list_buckets()  # 看 bucket 名是否在 path 里",
                "expected": "endpoint 配置正确，访问模式与 MinIO 配置一致",
                "judgment": "如果 SDK 默认用 vhost（bucket.域名）但 MinIO 未配置 domain，需统一用 path-style（域名/bucket）",
            },
            {
                "action": "如果是预签名 URL 问题，检查 nginx 代理的 Host header",
                "command": "# 检查 minio-nginx 配置\ncat /etc/nginx/conf.d/minio.conf | grep -i 'proxy_set_header\\|Host'",
                "expected": "proxy_set_header Host $http_host; （保留原始 Host）",
                "judgment": "如果 proxy_set_header Host 被改写为 $proxy_host 或固定值，预签名 URL 签名校验会失败，需改为 $http_host",
            },
            {
                "action": "用 mc 客户端直接测试 MinIO",
                "command": "# 配置 mc alias\nmc alias set <别名> http://<minio地址> <accesskey> <secretkey>\n# 列出 bucket\nmc ls <别名>/\n# 测试上传\nmc cp test.txt <别名>/<bucket>/test.txt",
                "expected": "能正常列出 bucket 和上传文件",
                "judgment": "如果 mc 也失败，问题在 MinIO 本身；如果 mc 成功但应用 SDK 失败，问题在 SDK 配置",
            },
            {
                "action": "统一对外入口（推荐方案）",
                "command": "# 用 minio-nginx 统一入口，所有请求走 nginx\n# nginx 配置关键项：\n# proxy_set_header Host $http_host;  # 保留签名用的 Host\n# proxy_pass http://minio_backend;",
                "expected": "应用通过 nginx 访问 MinIO，签名校验通过",
                "judgment": "这是 vhost vs path-style 问题的架构级解决方案",
            },
        ],
        "verify": "应用上传/下载文件成功，预签名 URL 可正常访问，无 500。",
        "rollback": "如果修改了 nginx 配置导致 MinIO 完全不可访问：\ncp /etc/nginx/conf.d/minio.conf.bak /etc/nginx/conf.d/minio.conf && nginx -s reload",
    },
    # ─────────────── 9. 磁盘满 ───────────────
    {
        "id": "disk-full",
        "title": "磁盘空间满排查",
        "keywords": ["disk full", "no space", "磁盘满", "no space left", "磁盘空间不足", "磁盘满了"],
        "summary": "磁盘空间不足，导致服务无法写入日志/数据/临时文件，可能引发各种连锁故障。",
        "root_causes": [
            {"cause": "日志文件未轮转/清理，持续增长撑满磁盘", "verify": "du -sh /var/log/* 找大文件", "probability": "高"},
            {"cause": "容器/Pod 的 emptyDir 或日志卷撑满节点磁盘", "verify": "du -sh /var/lib/docker/containers/*", "probability": "高"},
            {"cause": "业务数据未清理（临时文件、导出文件、上传文件堆积）", "verify": "du -sh 业务数据目录", "probability": "中"},
            {"cause": "coredump 文件堆积", "verify": "find / -name 'core.*' -size +100M", "probability": "低"},
        ],
        "steps": [
            {
                "action": "确认磁盘使用情况",
                "command": "df -h\n# 或查看具体挂载点\ndf -h /var/lib/docker",
                "expected": "Use% 列找出接近 100% 的挂载点",
                "judgment": "定位到哪个挂载点满了，针对性清理",
            },
            {
                "action": "定位大文件/大目录",
                "command": "# 找大文件\nfind / -type f -size +500M 2>/dev/null | head -20\n# 找大目录\ndu -sh /* 2>/dev/null | sort -rh | head -10\n# 针对性查\ndu -sh /var/log/* | sort -rh | head -10\ndu -sh /var/lib/docker/containers/* | sort -rh | head -10",
                "expected": "列出最大的文件/目录",
                "judgment": "根据类型清理：日志→轮转或删除旧日志；容器日志→配置 log rotation；数据→归档或删除",
            },
            {
                "action": "清理容器日志（Docker 环境）",
                "command": "# 清理已停止容器的日志（不删除运行中容器日志）\ntruncate -s 0 /var/lib/docker/containers/*/*-json.log\n# 配置 Docker 日志轮转（永久解决）\n# /etc/docker/daemon.json 加：\n# {\"log-driver\":\"json-file\",\"log-opts\":{\"max-size\":\"100m\",\"max-file\":\"3\"}}",
                "expected": "日志文件被截断，磁盘释放",
                "judgment": "truncate 不会影响运行中容器，安全操作",
            },
            {
                "action": "清理 K8s Pod 日志和 emptyDir",
                "command": "# 清理退出的 pod 日志\nfind /var/log/pods -type f -name '*.log' -mtime +7 -delete\n# 查看占用最多磁盘的 pod\ndu -sh /var/log/pods/* | sort -rh | head -10",
                "expected": "旧日志被清理",
                "judgment": "只清理 7 天前的日志，避免影响排查",
            },
            {
                "action": "清理系统日志和临时文件",
                "command": "# journal 日志限制\njournalctl --vacuum-size=500M\n# 临时文件\nfind /tmp -type f -atime +7 -delete\n# 包缓存\napt-get clean  # Debian/Ubuntu\nyum clean all  # CentOS",
                "expected": "系统日志和临时文件被清理",
                "judgment": "这些都是安全的清理操作",
            },
            {
                "action": "如果是业务数据堆积，归档而非删除",
                "command": "# 归档旧数据到其他存储\ntar -czf /backup/<目录>_$(date +%F).tar.gz <业务数据目录>/old/\n# 归档成功后删除原数据\nrm -rf <业务数据目录>/old/",
                "expected": "数据归档成功，磁盘释放",
                "judgment": "业务数据清理前必须先归档，避免数据丢失",
            },
        ],
        "verify": "df -h 显示磁盘使用率降到安全水位（<80%）。",
        "rollback": "删除操作不可逆。如果误删了重要文件：\n# 从备份恢复\n# 或如果用了 ext4，用 extundelete 尝试恢复（成功率低）\n# 预防：清理前先归档，不要直接 rm",
    },
    # ─────────────── 10. OOM Killed ───────────────
    {
        "id": "oom-killed",
        "title": "OOM Killed 排查",
        "keywords": ["oom", "out of memory", "内存溢出", "oomkilled", "oom killed", "内存不足", "memory"],
        "summary": "进程因内存使用超过限制被系统 kill（OOM Killer）。K8s 中表现为 pod 被 OOMKilled 后重启。",
        "root_causes": [
            {"cause": "应用内存泄漏（持续增长不释放）", "verify": "监控内存使用趋势，看是否持续上升", "probability": "高"},
            {"cause": "内存 limit 设置过低", "verify": "kubectl describe pod 看 limits", "probability": "高"},
            {"cause": "单次处理大内存数据（如加载大文件、大结果集）", "verify": "查看应用日志的 OOM 前操作", "probability": "中"},
            {"cause": "并发太高导致内存峰值超限", "verify": "监控并发量和内存峰值关系", "probability": "中"},
        ],
        "steps": [
            {
                "action": "确认是否 OOMKilled",
                "command": "kubectl describe pod <pod名> -n <namespace> | grep -A5 'Last State'",
                "expected": "Reason: OOMKilled, Exit Code: 137",
                "judgment": "确认是 OOM 后排查内存使用",
            },
            {
                "action": "查看内存 limit 和 request",
                "command": "kubectl describe pod <pod名> -n <namespace> | grep -A5 'Limits\\|Requests'",
                "expected": "memory limit 值",
                "judgment": "如果 limit 过低（如 256Mi 跑 Java 应用），调大到合理值",
            },
            {
                "action": "查看历史内存使用趋势",
                "command": "# 需要 metrics-server 或 Prometheus\nkubectl top pod <pod名> -n <namespace>\n# Prometheus 查询\n# container_memory_working_set_bytes{pod='<pod名>'}",
                "expected": "内存使用趋势（是否持续上升或峰值超限）",
                "judgment": "持续上升→内存泄漏；峰值超限→并发或大数据处理；稳定但接近 limit→limit 太低",
            },
            {
                "action": "查看应用日志，定位 OOM 前的操作",
                "command": "kubectl logs <pod名> -n <namespace> --previous --tail=100",
                "expected": "OOM 前最后的请求/操作日志",
                "judgment": "定位是哪个接口/操作触发了内存峰值，针对性优化",
            },
            {
                "action": "如果是 Java 应用，检查 JVM 堆配置",
                "command": "# 查看 JVM 参数\nkubectl exec <pod名> -n <namespace> -- jps -v 2>/dev/null | head -5\n# 或\nkubectl exec <pod名> -n <namespace> -- cat /proc/1/cmdline | tr '\\0' ' '",
                "expected": "-Xmx 值应小于 pod memory limit（建议留 25% 给非堆内存）",
                "judgment": "如果 -Xmx 接近 limit，非堆内存（Metaspace/线程栈/DirectBuffer）会导致 OOM，需调大 limit 或调小 -Xmx",
            },
            {
                "action": "如果是内存泄漏，抓堆 dump 分析",
                "command": "# Java\nkubectl exec <pod名> -n <namespace> -- jmap -dump:format=b,file=/tmp/heap.hprof <PID>\n# 拷贝出来\nkubectl cp <namespace>/<pod名>:/tmp/heap.hprof ./heap.hprof\n# 用 MAT/VisualVM 分析",
                "expected": "dump 文件生成，可用工具分析泄漏对象",
                "judgment": "MAT 分析后定位泄漏对象类型和调用链，修复代码",
            },
        ],
        "verify": "kubectl top pod 显示内存使用稳定在 limit 的 70% 以下，pod 不再 OOMKilled。",
        "rollback": "如果调大了 limit 但节点资源不足导致 pod 无法调度：\n# 回滚到原 limit\nkubectl set resources deployment/<deployment名> -n <namespace> --limits=memory=<原值>\n# 考虑扩容节点或优化应用内存使用",
    },
]


def list_runbooks():
    """列出所有 runbook 的 id、title、keywords。"""
    return [{"id": rb["id"], "title": rb["title"], "keywords": rb["keywords"]} for rb in RUNBOOKS]


def get_runbook(rb_id):
    """根据 id 获取单个 runbook 完整内容。"""
    for rb in RUNBOOKS:
        if rb["id"] == rb_id:
            return rb
    return None


def match_runbook(query):
    """根据关键词/自然语言匹配最相关的 runbook。
    返回匹配度最高的 runbook，无匹配返回 None。
    """
    if not query:
        return None
    query_lower = query.lower().strip()
    best_match = None
    best_score = 0
    for rb in RUNBOOKS:
        score = 0
        for kw in rb["keywords"]:
            kw_lower = kw.lower()
            if kw_lower in query_lower:
                score += len(kw_lower)  # 关键词越长权重越高
            if query_lower in kw_lower:
                score += len(query_lower) * 2  # 精确匹配权重更高
        # id 也参与匹配
        if rb["id"].lower() in query_lower:
            score += len(rb["id"])
        if query_lower == rb["id"].lower():
            score += 50
        if score > best_score:
            best_score = score
            best_match = rb
    return best_match if best_score > 0 else None


# ============================================================
# 独立运行入口：python runbook_lib.py --list
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runbook Library 查看工具")
    parser.add_argument("--list", action="store_true", help="列出所有 runbook")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.list:
        data = list_runbooks()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"共 {len(data)} 个 runbook：\n")
            for rb in data:
                print(f"  {rb['id']:25s}  {rb['title']}")
                print(f"  {'':25s}  关键词: {', '.join(rb['keywords'])}\n")
    else:
        parser.print_help()
