#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue Report Formatter · 运维问题上报格式化器核心脚本

三种工作模式：
1. --mode extract  : 从自然语言描述中抽取关键字段，生成结构化报告
2. --mode format   : 把用户逐字段提供的输入格式化为标准报告
3. --mode assist   : 格式化报告后，生成 AI 协作提示词+排查清单+诊断假设树（同步给 AI 辅助解决）

输出：Markdown 报告（stdout）+ JSON 结构化数据（--json 参数指定文件路径）

安全边界：
- 抽取不到的字段标记 [待补充]，绝不臆造
- 不执行任何命令、不调用任何 API、不修改任何配置
- 敏感信息（IP/密码）默认保留，--mask 参数可脱敏
- assist 模式只生成提示词，不直接调 AI API
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta


# ============================================================
# 字段抽取规则（对话式模式）
# ============================================================

# 已知客户名（可扩展）——匹配到这些词时优先识别为客户名
KNOWN_CUSTOMERS = [
    "字节跳动", "江西铜业", "七天网络", "浙江白马",
    "汇洲智能", "五环绿能", "EnableAI", "enableai",
]

# 环境/节点匹配模式
NODE_PATTERNS = [
    r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?\b',          # IP[:端口]
    r'\b(qm-prod|qm-admin|qm-core|minio\d*|minio-nginx)\b',            # 已知主机名
    r'\b(enableai|wuwen|kube-system|default)\b\s*(?:namespace)?',     # K8s namespace
    r'(?:(生产|测试|开发|预发|staging|prod|test|dev)[环境]?)',         # 环境名
]

# 报错匹配模式
ERROR_PATTERNS = [
    r'(?:返回|响应|状态码|HTTP)\s*[:：]?\s*(\d{3})\s*(.+?)?(?=[，。；,;]|$)',
    r'(HTTP/\d(?:\.\d)?\s+\d{3}\s+.+)',
    r'((?:core_unreachable|connection refused|timeout|超时|宕机|不可用|502|503|504|500|404|403|401)\b[^，。；,;\n]{0,80})',
    r'((?:Error|Exception|Failed|Traceback)[:：]?\s*.+)',
]

# 已试操作匹配
TRIED_PATTERNS = [
    r'(?:已试过|已经试过|试过|重启过|检查过|排查过|重新|已经)([^，。；,;\n]{2,80})',
    r'(?:操作[:：])\s*([^，。；,;\n]{2,80})',
]

# 复现步骤匹配
REPRODUCE_PATTERNS = [
    r'(?:复现|重现|触发|步骤)[:：]?\s*(.+?)(?=(?:已试|建议|紧急|$))',
    r'(?:curl|wget|docker|kubectl|ssh|ping)\s+[^，。\n]{2,100}',
]


def extract_customer(text: str) -> str:
    """抽取客户名"""
    for customer in KNOWN_CUSTOMERS:
        if customer in text:
            return customer
    # 匹配 "客户XX" / "XX项目" / "为XX"
    m = re.search(r'客户[:：]?\s*([\u4e00-\u9fa5a-zA-Z]{2,20})', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'([\u4e00-\u9fa5]{2,10})项目', text)
    if m:
        return m.group(1).strip()
    return "[待补充]"


def extract_node(text: str) -> str:
    """抽取环境/节点"""
    parts = []
    # 环境
    env_match = re.search(r'(生产|测试|开发|预发|staging|prod|test|dev)', text, re.IGNORECASE)
    if env_match:
        parts.append(env_match.group(1))
    # IP
    for pattern in NODE_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            for m in matches:
                if isinstance(m, tuple):
                    node = ":".join(x for x in m if x)
                else:
                    node = m
                if node and node not in parts:
                    parts.append(node)
            break
    # 主机名/namespace
    for pattern in [r'\b(qm-prod|qm-admin|qm-core|minio\d*|minio-nginx)\b',
                    r'\b(enableai|wuwen|kube-system)\b']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if m.lower() not in [p.lower() for p in parts]:
                parts.append(m)
    return " / ".join(parts) if parts else "[待补充]"


def extract_error(text: str) -> str:
    """抽取完整报错"""
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # 合并所有匹配到的报错片段
            error_parts = []
            for m in matches:
                if isinstance(m, tuple):
                    err = " ".join(x for x in m if x)
                else:
                    err = m
                if err and err not in error_parts:
                    error_parts.append(err.strip())
            if error_parts:
                return " | ".join(error_parts[:3])  # 最多取 3 条
    return "[待补充]"


def extract_tried(text: str) -> str:
    """抽取已试操作"""
    tried_parts = []
    for pattern in TRIED_PATTERNS:
        matches = re.findall(pattern, text)
        for m in matches:
            m = m.strip()
            if m and m not in tried_parts and len(m) >= 2:
                tried_parts.append(m)
    return "；".join(tried_parts) if tried_parts else "[待补充]"


def extract_reproduce(text: str) -> str:
    """抽取复现步骤"""
    for pattern in REPRODUCE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        if matches:
            steps = []
            for m in matches:
                if isinstance(m, tuple):
                    step = m[0].strip()
                else:
                    step = m.strip()
                if step and step not in steps:
                    steps.append(step)
            if steps:
                return "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps[:5]))
    return "[偶发，未稳定复现]" if "偶发" in text else "[待补充]"


def extract_from_text(text: str) -> dict:
    """对话式：从自然语言抽取所有字段"""
    # 先抽取已试操作，并从原文中剥离，避免 error 抽取时吸入"已试过..."内容
    tried = extract_tried(text)
    text_without_tried = re.sub(
        r'(?:已试过|已经试过|试过|重启过|检查过|排查过|重新|已经)[^，。；,;\n]{2,80}',
        '',
        text
    )
    return {
        "customer": extract_customer(text),
        "environment": extract_node(text),
        "error": extract_error(text_without_tried),
        "tried": tried,
        "reproduce": extract_reproduce(text),
        "raw_input": text[:200] + "..." if len(text) > 200 else text,
    }


# ============================================================
# 紧急度分级
# ============================================================

def classify_severity(fields: dict) -> tuple:
    """
    根据字段内容自动分级
    返回 (level, reason)
    """
    text = " ".join(str(v) for v in fields.values()).lower()

    # 紧急关键词
    urgent_keywords = ["502", "503", "504", "500", "宕机", "不可用", "core_unreachable",
                       "connection refused", "超时", "timeout", "数据丢失", "生产", "prod"]
    important_keywords = ["404", "403", "401", "异常", "失败", "报错", "error", "failed"]
    normal_keywords = ["咨询", "建议", "优化", "文档", "问题", "请问"]

    urgent_hits = sum(1 for k in urgent_keywords if k in text)
    important_hits = sum(1 for k in important_keywords if k in text)
    normal_hits = sum(1 for k in normal_keywords if k in text)

    # 生产环境 + 核心服务不可用 → 紧急
    if "生产" in text or "prod" in text:
        if urgent_hits >= 2:
            return "🔴 紧急", "生产环境 + 核心服务异常（含 5xx/宕机/超时）"
        if important_hits >= 1:
            return "🟡 重要", "生产环境 + 部分功能异常"
    # 非生产环境核心服务不可用 → 重要
    if urgent_hits >= 2:
        return "🟡 重要", "非生产环境但核心服务异常"
    # 仅咨询/优化 → 普通
    if normal_hits >= 2 and urgent_hits == 0:
        return "🟢 普通", "非生产环境 + 咨询/优化类"
    # 默认普通
    return "🟢 普通", "未匹配紧急/重要关键词，默认普通"


def generate_suggestions(fields: dict) -> list:
    """基于报错特征生成排查建议（启发式，非诊断）"""
    suggestions = []
    error = fields.get("error", "").lower()
    node = fields.get("environment", "")

    if "502" in error or "core_unreachable" in error:
        suggestions.append("检查上游服务是否真的起来（netstat -tlnp / ss -tlnp）")
        suggestions.append("检查下游到上游的网络连通性（curl/ping）")
        suggestions.append("查看上游服务日志最近的 ERROR/Exception")
    elif "503" in error or "504" in error:
        suggestions.append("检查服务是否过载（top/htop 查 CPU/内存）")
        suggestions.append("检查连接池/线程池是否打满")
        suggestions.append("查看 ingress/nginx 的 access log 和 error log")
    elif "timeout" in error or "超时" in error:
        suggestions.append("检查网络延迟和带宽（traceroute/iperf）")
        suggestions.append("检查服务端处理耗时（慢查询/锁等待）")
        suggestions.append("确认超时配置是否合理（client/server timeout）")
    elif "connection refused" in error:
        suggestions.append("确认目标端口是否在监听（ss/netstat）")
        suggestions.append("检查防火墙/安全组规则")
        suggestions.append("确认服务进程是否存活（ps/systemctl status）")
    elif "404" in error:
        suggestions.append("确认请求路径/路由是否正确")
        suggestions.append("检查 ingress/路由配置")
    elif "403" in error or "401" in error:
        suggestions.append("检查认证信息（token/cookie/API key）是否有效")
        suggestions.append("确认权限配置是否正确")
    else:
        suggestions.append("查看相关服务的完整日志")
        suggestions.append("检查最近是否有变更（部署/配置/证书更新）")
        suggestions.append("确认问题是否可稳定复现")

    return suggestions[:3]  # 最多 3 条


# ============================================================
# 报告生成
# ============================================================

def mask_sensitive(text: str) -> str:
    """脱敏：IP 保留前两段，密码/token 替换"""
    # IP 脱敏：保留前两段
    text = re.sub(r'(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}', r'\1.x.x', text)
    # 密码/token
    text = re.sub(r'(password|passwd|token|secret|api[_-]?key)[:：]\s*\S+', r'\1: [REDACTED]', text, flags=re.IGNORECASE)
    return text


def generate_markdown_report(fields: dict, severity: str, severity_reason: str,
                             suggestions: list, enable_monetization: bool = True) -> str:
    """生成 Markdown 报告"""
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S +08:00")

    report = f"""## 问题上报

- **客户名**：{fields['customer']}
- **环境/节点**：{fields['environment']}
- **完整报错**：{fields['error']}
- **已试操作**：{fields['tried']}
- **复现步骤**：
{fields['reproduce']}
- **紧急度**：{severity}（自动分级，请人工复核）
  - 分级依据：{severity_reason}
- **建议下一步**：
"""
    for i, s in enumerate(suggestions, 1):
        report += f"  {i}. {s}\n"

    report += f"\n- **上报时间**：{now}\n"

    if enable_monetization:
        report += """
---
💡 需要专业运维支持？根因排查/代维服务可联系：[你的联系方式]
📚 更多运维实战内容 → 公众号：[你的公众号名]
"""

    return report


def generate_json(fields: dict, severity: str, suggestions: list) -> dict:
    """生成 JSON 结构化数据（不含变现引导，保证数据干净）"""
    severity_level = severity.split()[1] if " " in severity else "unknown"
    return {
        "customer": fields["customer"],
        "environment": fields["environment"],
        "error": fields["error"],
        "tried": fields["tried"],
        "reproduce": fields["reproduce"],
        "severity": severity_level,
        "suggestions": suggestions,
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    }


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="运维问题上报格式化器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 对话式：从自然语言抽取
  echo "qm-prod 上 qm-admin 8090 的 /api/whoami 返回 502 core_unreachable，core 服务位于 8080，已试过重启 core" | python format_report.py --mode extract

  # 表单式：逐字段提供
  python format_report.py --mode format --customer "浙江白马" --env "生产/172.22.1.22" --error "502 core_unreachable" --tried "重启 core"

  # 输出 JSON 到文件
  python format_report.py --mode extract --json report.json

  # 脱敏模式（导出到外部时用）
  python format_report.py --mode extract --mask

  # 关闭变现引导
  python format_report.py --mode extract --no-monetization
"""
    )
    parser.add_argument("--mode", choices=["extract", "format", "assist"], required=True,
                        help="extract=从自然语言抽取，format=逐字段格式化，assist=格式化+生成AI协作提示词")
    parser.add_argument("--customer", help="[format 模式] 客户名")
    parser.add_argument("--env", help="[format 模式] 环境/节点")
    parser.add_argument("--error", help="[format 模式] 完整报错")
    parser.add_argument("--tried", help="[format 模式] 已试操作")
    parser.add_argument("--reproduce", help="[format 模式] 复现步骤")
    parser.add_argument("--json", dest="json_path", help="JSON 输出文件路径")
    parser.add_argument("--mask", action="store_true", help="脱敏模式（IP/密码）")
    parser.add_argument("--no-monetization", action="store_true", help="关闭变现引导")
    args = parser.parse_args()

    # 收集字段
    if args.mode == "extract" or args.mode == "assist":
        # extract 和 assist 都从 stdin 读取自然语言
        text = sys.stdin.read().strip()
        if not text:
            print("[错误] extract/assist 模式需要从 stdin 输入自然语言描述", file=sys.stderr)
            sys.exit(1)
        fields = extract_from_text(text)
    else:
        # format 模式：逐字段收集
        fields = {
            "customer": args.customer or "[待补充]",
            "environment": args.env or "[待补充]",
            "error": args.error or "[待补充]",
            "tried": args.tried or "[待补充]",
            "reproduce": args.reproduce or "[待补充]",
        }

    # 脱敏
    if args.mask:
        for k, v in fields.items():
            if isinstance(v, str) and v != "[待补充]":
                fields[k] = mask_sensitive(v)

    # 紧急度分级
    severity, reason = classify_severity(fields)

    # 生成建议
    suggestions = generate_suggestions(fields)

    # 生成报告
    enable_mon = not args.no_monetization
    md_report = generate_markdown_report(fields, severity, reason, suggestions, enable_mon)

    # 输出 Markdown 到 stdout
    print(md_report)

    # assist 模式：额外输出 AI 协作产物
    if args.mode == "assist":
        try:
            from generate_ai_prompt import generate_assist_output
            print("\n" + generate_assist_output(fields, severity))
        except ImportError:
            # 独立运行 generate_ai_prompt.py 时走 subprocess
            import subprocess
            json_str = json.dumps(fields, ensure_ascii=False)
            result = subprocess.run(
                [sys.executable, "generate_ai_prompt.py", "--json-input", json_str, "--severity", severity],
                capture_output=True, text=True, encoding="utf-8"
            )
            print("\n" + result.stdout)

    # 输出 JSON 到文件（如果指定）
    if args.json_path:
        json_data = generate_json(fields, severity, suggestions)
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"\n[JSON 已保存到 {args.json_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
