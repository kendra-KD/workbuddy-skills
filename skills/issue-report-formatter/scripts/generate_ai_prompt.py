#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Prompt Generator · AI 协作提示词生成器

接收一份结构化的问题上报字段（dict 或 JSON），生成三份 AI 协作产物：
1. 结构化提示词（复制粘贴给任意 AI 即可）
2. 排查 checklist（要查什么、怎么查、用什么命令）
3. 诊断假设树（可能原因 + 验证方法，引导 AI 按"先列假设→跑诊断→解读"流程）

可独立使用，也可被 format_report.py --mode assist 调用。

使用示例：
  # 从 stdin 读 JSON
  echo '{"customer":"客户A","environment":"生产/10.0.1.5","error":"502 service_unavailable","tried":"重启 core","reproduce":"curl /api/health"}' | python generate_ai_prompt.py

  # 独立测试（内置示例）
  python generate_ai_prompt.py --demo
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta


# ============================================================
# 排查 checklist 生成（基于报错类型）
# ============================================================

def generate_checklist(fields: dict) -> list:
    """基于报错特征生成排查 checklist（每项含：检查什么 + 怎么查 + 命令）"""
    error = (fields.get("error") or "").lower()
    env = fields.get("environment") or ""
    checklist = []

    if "502" in error or "service_unavailable" in error:
        checklist = [
            {"item": "上游服务是否在监听", "how": "检查目标端口是否 LISTEN", "cmd": "ss -tlnp | grep <port> 或 netstat -tlnp | grep <port>"},
            {"item": "服务进程是否存活", "how": "确认进程在运行且未僵尸", "cmd": "ps aux | grep <service> 或 systemctl status <service>"},
            {"item": "网络连通性", "how": "从调用方到被调方的网络是否通", "cmd": "curl -v http://<ip>:<port>/health 或 ping <ip>"},
            {"item": "上游服务日志", "how": "查最近 ERROR/Exception/Traceback", "cmd": "journalctl -u <service> --since '30 min ago' | grep -i error 或 tail -100 <log_path>"},
            {"item": "反向代理/ingress 配置", "how": "nginx/ingress 是否正确转发到上游", "cmd": "nginx -T | grep -A5 <location> 或 kubectl describe ingress <name>"},
        ]
    elif "503" in error or "504" in error:
        checklist = [
            {"item": "服务是否过载", "how": "查 CPU/内存/连接数", "cmd": "top -bn1 | head -20 或 free -h 或 ss -s"},
            {"item": "连接池/线程池状态", "how": "是否打满", "cmd": "查看应用监控面板或 ss -tnp | wc -l"},
            {"item": "网关层日志", "how": "nginx/ingress access log + error log", "cmd": "tail -100 /var/log/nginx/error.log 或 kubectl logs <nginx-pod>"},
            {"item": "超时配置", "how": "client/server timeout 是否合理", "cmd": "nginx -T | grep -i timeout 或查应用配置"},
            {"item": "上游健康检查", "how": "上游是否被标记为 down", "cmd": "查负载均衡健康检查状态"},
        ]
    elif "timeout" in error or "超时" in error:
        checklist = [
            {"item": "网络延迟", "how": "端到端延迟", "cmd": "traceroute <ip> 或 ping -c 10 <ip>"},
            {"item": "服务端处理耗时", "how": "是否有慢查询/锁等待", "cmd": "查慢查询日志或 APM trace"},
            {"item": "带宽是否打满", "how": "网卡流量", "cmd": "iftop 或 nethogs 或 sar -n DEV"},
            {"item": "超时阈值配置", "how": "client/server timeout 设置", "cmd": "查配置文件 timeout 相关项"},
            {"item": "DNS 解析延迟", "how": "DNS 解析是否慢", "cmd": "dig <domain> +trace 或 nslookup <domain>"},
        ]
    elif "connection refused" in error:
        checklist = [
            {"item": "目标端口是否监听", "how": "端口是否 LISTEN", "cmd": "ss -tlnp | grep <port>"},
            {"item": "服务进程是否存活", "how": "进程在不在", "cmd": "ps aux | grep <service>"},
            {"item": "防火墙/安全组", "how": "端口是否被拦截", "cmd": "iptables -L -n 或云安全组规则"},
            {"item": "服务绑定地址", "how": "是否只绑了 127.0.0.1", "cmd": "ss -tlnp | grep <port> 看绑定地址"},
            {"item": "服务启动日志", "how": "启动时是否报错", "cmd": "journalctl -u <service> --since '1 hour ago'"},
        ]
    elif "404" in error:
        checklist = [
            {"item": "请求路径是否正确", "how": "URL 路径拼写/大小写", "cmd": "核对 API 文档"},
            {"item": "路由配置", "how": "ingress/nginx 路由规则", "cmd": "kubectl describe ingress <name> 或 nginx -T | grep location"},
            {"item": "服务版本", "how": "接口是否在新版本才加", "cmd": "查服务版本和 changelog"},
            {"item": "资源是否真的存在", "how": "查的具体 ID 是否存在", "cmd": "直接查数据库或存储"},
        ]
    elif "403" in error or "401" in error:
        checklist = [
            {"item": "认证信息是否有效", "how": "token/cookie/API key 是否过期", "cmd": "用新 token 测试"},
            {"item": "权限配置", "how": "账号是否有对应权限", "cmd": "查权限配置表"},
            {"item": "时间同步", "how": "服务器时间是否正确（影响 token 校验）", "cmd": "date 或 ntpstat"},
            {"item": "CORS 配置", "how": "跨域是否允许", "cmd": "curl -v -X OPTIONS 检查响应头"},
        ]
    else:
        checklist = [
            {"item": "服务完整日志", "how": "最近的 ERROR/WARN", "cmd": "tail -200 <log_path> | grep -iE 'error|warn|exception'"},
            {"item": "最近变更", "how": "是否有部署/配置/证书更新", "cmd": "查 CI/CD 记录或 git log"},
            {"item": "监控指标", "how": "CPU/内存/磁盘/网络异常", "cmd": "查 Prometheus/Grafana 面板"},
            {"item": "复现条件", "how": "是否能稳定复现", "cmd": "按上报的复现步骤手动触发"},
            {"item": "依赖服务状态", "how": "数据库/缓存/MQ 是否正常", "cmd": "ping/curl 各依赖端点"},
        ]

    # 如果有已知已试操作，加一条"避免重复"
    tried = fields.get("tried") or ""
    if tried and tried != "[待补充]":
        checklist.append({
            "item": "已试操作的结果（避免重复排查）",
            "how": f"用户已试过：{tried}，需确认结果",
            "cmd": "向用户确认上述操作的结果",
        })

    return checklist


# ============================================================
# 诊断假设树生成
# ============================================================

def generate_hypothesis_tree(fields: dict) -> list:
    """
    生成诊断假设树：列出可能原因 + 验证方法 + 预期结果
    结构：[{hypothesis, verify_how, expected_if_true, expected_if_false}]
    """
    error = (fields.get("error") or "").lower()
    hypotheses = []

    if "502" in error or "service_unavailable" in error:
        hypotheses = [
            {
                "hypothesis": "上游服务没起来或崩了",
                "verify_how": "检查目标端口是否在 LISTEN + 进程是否存活",
                "expected_if_true": "端口未监听 / 进程不存在 → 服务确实挂了",
                "expected_if_false": "端口在监听 / 进程在 → 排除此假设，往下查",
            },
            {
                "hypothesis": "上游服务起来了但内部异常（连不上数据库/依赖）",
                "verify_how": "查上游服务日志的 ERROR + 健康检查端点",
                "expected_if_true": "日志有 ERROR / 健康检查返回非 200 → 内部异常",
                "expected_if_false": "日志无异常 / 健康检查 200 → 内部正常，往下查",
            },
            {
                "hypothesis": "网络层问题（防火墙/安全组/路由）",
                "verify_how": "从调用方 curl/ping 上游，检查防火墙规则",
                "expected_if_true": "不通 → 网络层问题",
                "expected_if_false": "通 → 网络正常，往下查",
            },
            {
                "hypothesis": "反向代理/ingress 配置错误（转发到错误端口/地址）",
                "verify_how": "检查 nginx/ingress 的 upstream/proxy_pass 配置",
                "expected_if_true": "配置指向错误端口 → 配置问题",
                "expected_if_false": "配置正确 → 往下查",
            },
        ]
    elif "503" in error or "504" in error:
        hypotheses = [
            {"hypothesis": "服务过载（CPU/内存/连接打满）", "verify_how": "查系统指标", "expected_if_true": "指标飙高 → 过载", "expected_if_false": "指标正常 → 往下查"},
            {"hypothesis": "上游响应慢（慢查询/锁等待）", "verify_how": "查 APM/慢查询日志", "expected_if_true": "有慢查询 → 上游慢", "expected_if_false": "无慢查询 → 往下查"},
            {"hypothesis": "超时配置不合理", "verify_how": "查 nginx/应用 timeout 配置", "expected_if_true": "timeout 太短 → 配置问题", "expected_if_false": "timeout 合理 → 往下查"},
            {"hypothesis": "连接池打满", "verify_how": "查连接池监控", "expected_if_true": "连接池满 → 容量问题", "expected_if_false": "连接池有空闲 → 往下查"},
        ]
    elif "timeout" in error or "超时" in error:
        hypotheses = [
            {"hypothesis": "网络延迟/抖动", "verify_how": "traceroute/ping", "expected_if_true": "延迟高 → 网络", "expected_if_false": "延迟低 → 往下查"},
            {"hypothesis": "服务端处理慢", "verify_how": "APM trace / 慢查询日志", "expected_if_true": "处理耗时长 → 服务端慢", "expected_if_false": "处理快 → 往下查"},
            {"hypothesis": "带宽打满", "verify_how": "iftop/sar -n DEV", "expected_if_true": "带宽满 → 容量", "expected_if_false": "带宽够 → 往下查"},
            {"hypothesis": "DNS 解析慢", "verify_how": "dig/nslookup", "expected_if_true": "解析慢 → DNS", "expected_if_false": "解析快 → 往下查"},
        ]
    elif "connection refused" in error:
        hypotheses = [
            {"hypothesis": "服务没启动", "verify_how": "ps/systemctl status", "expected_if_true": "进程不在 → 没启动", "expected_if_false": "进程在 → 往下查"},
            {"hypothesis": "端口未监听", "verify_how": "ss/netstat", "expected_if_true": "端口未 LISTEN → 未监听", "expected_if_false": "端口 LISTEN → 往下查"},
            {"hypothesis": "绑定了 127.0.0.1（外部访问不了）", "verify_how": "ss -tlnp 看绑定地址", "expected_if_true": "绑了 127.0.0.1 → 绑定问题", "expected_if_false": "绑了 0.0.0.0 → 往下查"},
            {"hypothesis": "防火墙拦截", "verify_how": "iptables -L / 安全组", "expected_if_true": "规则拦截 → 防火墙", "expected_if_false": "无拦截 → 往下查"},
        ]
    else:
        hypotheses = [
            {"hypothesis": "应用层错误（代码 bug/配置错误）", "verify_how": "查应用日志 ERROR + 配置文件", "expected_if_true": "日志有 ERROR → 应用层", "expected_if_false": "无 → 往下查"},
            {"hypothesis": "依赖服务异常（DB/缓存/MQ）", "verify_how": "ping/curl 各依赖", "expected_if_true": "依赖不通 → 依赖问题", "expected_if_false": "依赖正常 → 往下查"},
            {"hypothesis": "资源瓶颈（CPU/内存/磁盘）", "verify_how": "top/free/df", "expected_if_true": "资源满 → 瓶颈", "expected_if_false": "资源够 → 往下查"},
            {"hypothesis": "最近变更引入", "verify_how": "查部署记录/git log", "expected_if_true": "有变更 → 变更引入", "expected_if_false": "无变更 → 往下查"},
        ]

    return hypotheses


# ============================================================
# 结构化提示词生成（复制粘贴给 AI）
# ============================================================

def generate_prompt(fields: dict, severity_label: str, checklist: list, hypotheses: list) -> str:
    """生成可直接粘贴给任意 AI 的结构化提示词"""
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S +08:00")

    # checklist 转 markdown
    checklist_md = ""
    for i, item in enumerate(checklist, 1):
        checklist_md += f"  {i}. **{item['item']}** — {item['how']}\n     命令：`{item['cmd']}`\n"

    # 假设树转 markdown
    hypo_md = ""
    for i, h in enumerate(hypotheses, 1):
        hypo_md += f"  {i}. 假设：{h['hypothesis']}\n     验证方法：{h['verify_how']}\n     若成立：{h['expected_if_true']}\n     若不成立：{h['expected_if_false']}\n"

    prompt = f"""# 角色与任务
你是一位资深运维/SRE 专家。请帮我排查以下已上报的故障。
请按『先列假设 → 跑诊断命令 → 解读结论 → 给修复方案』的流程推进，每一步等我确认后再做下一步。
不要一上来就给"重启试试"这种没有根因分析的方案。

# 故障上报信息
- **客户名**：{fields.get('customer', '[待补充]')}
- **环境/节点**：{fields.get('environment', '[待补充]')}
- **完整报错**：{fields.get('error', '[待补充]')}
- **已试操作**：{fields.get('tried', '[待补充]')}
- **复现步骤**：
{fields.get('reproduce', '[待补充]')}
- **紧急度**：{severity_label}（上报时间 {now}）

# 我希望你做的
1. **先读上面的上报信息**，如果有缺失关键字段，先问我补充，不要臆造
2. **基于报错特征，我已整理了一份排查 checklist 和诊断假设树**（见下方），请参考但不必局限
3. **按假设树逐个验证**：先给我第一个假设的验证命令，我跑完把输出贴给你，你解读后再给下一个
4. **结论用结构化输出**：根因 / 修复方案 / 预防措施，每条附理由
5. **安全约束**：不要建议任何可能破坏现有服务的操作（如 rm -rf / 强制重启 / 删除数据库），涉及高危操作请先标注风险等我确认
# 排查 Checklist（参考，不必全跑）
{checklist_md}

# 诊断假设树（按顺序验证，验证完一个再下一个）
{hypo_md}

# 现在开始
请先读上报信息，告诉我：
1. 你认为最可能的根因（top 2），附理由
2. 你建议先验证哪个假设，给我具体的诊断命令
"""
    return prompt


# ============================================================
# 输出格式化
# ============================================================

def generate_assist_output(fields: dict, severity_label: str = "") -> str:
    """生成完整的 assist 模式输出（提示词 + checklist + 假设树）"""
    checklist = generate_checklist(fields)
    hypotheses = generate_hypothesis_tree(fields)

    prompt = generate_prompt(fields, severity_label or "🟡 待分级", checklist, hypotheses)

    output = "=" * 60 + "\n"
    output += "📋 【产物 1】结构化提示词（复制粘贴给任意 AI）\n"
    output += "=" * 60 + "\n"
    output += prompt + "\n\n"

    output += "=" * 60 + "\n"
    output += "🔍 【产物 2】排查 Checklist（你也可以自己照着查）\n"
    output += "=" * 60 + "\n"
    for i, item in enumerate(checklist, 1):
        output += f"{i}. {item['item']}\n   怎么查：{item['how']}\n   命令：{item['cmd']}\n\n"

    output += "=" * 60 + "\n"
    output += "🌳 【产物 3】诊断假设树（引导 AI 按『先列假设→跑诊断→解读』流程）\n"
    output += "=" * 60 + "\n"
    for i, h in enumerate(hypotheses, 1):
        output += f"假设 {i}：{h['hypothesis']}\n"
        output += f"  验证：{h['verify_how']}\n"
        output += f"  若成立：{h['expected_if_true']}\n"
        output += f"  若不成立：{h['expected_if_false']}\n\n"

    output += "=" * 60 + "\n"
    output += "💡 使用说明\n"
    output += "=" * 60 + "\n"
    output += "1. 把【产物 1】整段复制粘贴给 ChatGPT/Claude/WorkBuddy 等任意 AI\n"
    output += "2. AI 会按『先列假设→给诊断命令→解读输出→给方案』的流程辅助你排查\n"
    output += "3. 你也可以自己照【产物 2】的 checklist 逐项查\n"
    output += "4. 【产物 3】的假设树是给 AI 的『思考框架』，确保它不跳步\n"

    return output


# ============================================================
# 主入口
# ============================================================

DEMO_FIELDS = {
    "customer": "客户A",
    "environment": "生产 / 10.0.1.5 / production",
    "error": "app-service 8090 /api/health 返回 502 service_unavailable",
    "tried": "重启 core 服务 8080，问题未解决",
    "reproduce": "curl http://10.0.1.5:8090/api/health → 502",
}


def main():
    parser = argparse.ArgumentParser(
        description="AI 协作提示词生成器（assist 模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 从 stdin 读 JSON（配合 format_report.py --json 使用）
  cat report.json | python generate_ai_prompt.py

  # 直接传 JSON 字符串
  python generate_ai_prompt.py --json-input '{"customer":"客户A","error":"502"}'

  # 内置示例（快速看效果）
  python generate_ai_prompt.py --demo
"""
    )
    parser.add_argument("--json-input", help="直接传 JSON 字符串")
    parser.add_argument("--demo", action="store_true", help="使用内置示例")
    parser.add_argument("--severity", default="", help="紧急度标签（可选）")
    args = parser.parse_args()

    if args.demo:
        fields = DEMO_FIELDS
        print(generate_assist_output(fields, "🔴 紧急"))
        return

    if args.json_input:
        fields = json.loads(args.json_input)
    else:
        # 从 stdin 读
        raw = sys.stdin.read().strip()
        if not raw:
            print("[错误] 请通过 --json-input / --demo / stdin 提供数据", file=sys.stderr)
            sys.exit(1)
        fields = json.loads(raw)

    print(generate_assist_output(fields, args.severity))


if __name__ == "__main__":
    main()
