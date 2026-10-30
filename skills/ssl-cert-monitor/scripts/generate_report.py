#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSL Cert Monitor - 报告生成脚本
读取 check_certs.py 产出的 JSON，生成按紧急程度排序的 Markdown 表格报告。

只用 Python 标准库（json + datetime），不依赖第三方包。

用法：
    python generate_report.py --input check_result.json --output report.md
    python generate_report.py --input check_result.json
    python generate_report.py < check_result.json > report.md

输入 JSON 结构（由 check_certs.py 产出）：
    {
        "check_time": "2026-10-30T10:00:00Z",
        "total": 10,
        "success": 8,
        "failed": 2,
        "urgent_count": 1,
        "warning_count": 3,
        "results": [
            { "domain": ..., "port": ..., "status": ..., "urgency": ..., ... }
        ]
    }

输出：
    Markdown 文件，含汇总统计表 + 按紧急度排序的明细表 + 续签指引链接。
"""

import argparse
import json
import sys
from datetime import datetime, timezone

# 紧急程度阈值（与 check_certs.py 保持一致）
URGENT_DAYS = 7
WARNING_DAYS = 30

# 紧急程度排序权重：expired > urgent > warning > normal > error
URGENCY_ORDER = {
    "expired": 0,
    "urgent": 1,
    "warning": 2,
    "normal": 3,
    None: 9,  # error 状态的 urgency 为 None，排最后
}

# 状态中文映射
STATUS_LABEL = {
    "ok": "正常",
    "expired": "已过期",
    "error": "检查失败",
}

# 紧急程度中文映射 + Emoji
URGENCY_LABEL = {
    "urgent": "🔴 紧急",
    "warning": "🟡 警告",
    "normal": "🟢 正常",
    "expired": "🔴 已过期",
    None: "⚪ 未知",
}

# 错误类型中文映射
ERROR_LABEL = {
    "timeout": "连接超时",
    "dns_resolve_failed": "DNS 解析失败",
    "connection_refused": "端口未开放（连接被拒绝）",
    "no_certificate": "无 TLS 证书（可能为 HTTP 服务）",
    "ssl_error": "SSL/TLS 握手失败",
    "unknown": "未知错误",
}


def format_datetime(iso_str):
    """将 ISO8601 时间转为本地可读格式（YYYY-MM-DD HH:MM UTC）。"""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return iso_str


def format_san(san_list):
    """格式化 SAN 列表：超过 3 个时只显示前 3 个 + '等 N 个'。"""
    if not san_list:
        return "-"
    if len(san_list) <= 3:
        return ", ".join(san_list)
    return ", ".join(san_list[:3]) + f" 等 {len(san_list)} 个"


def sort_results(results):
    """按紧急程度排序：expired > urgent > warning > normal > error。"""
    def sort_key(r):
        urgency = r.get("urgency")
        urgency_rank = URGENCY_ORDER.get(urgency, 9)
        # 同紧急程度内，按剩余天数升序（天数少的排前面）
        days = r.get("days_remaining")
        if days is None:
            days = 99999  # 无天数的（error）排同组最后
        return (urgency_rank, days)
    return sorted(results, key=sort_key)


def generate_summary_section(data):
    """生成汇总统计章节。"""
    check_time = format_datetime(data.get("check_time"))
    total = data.get("total", 0)
    success = data.get("success", 0)
    failed = data.get("failed", 0)
    urgent = data.get("urgent_count", 0)
    warning = data.get("warning_count", 0)

    # 分类统计：expired 单独算，normal = success - urgent - warning - expired
    expired_count = len([r for r in data.get("results", []) if r.get("status") == "expired"])
    normal_count = success - urgent - warning - expired_count
    if normal_count < 0:
        normal_count = 0

    lines = [
        "## 汇总统计",
        "",
        "| 项目 | 数量 |",
        "|------|------|",
        f"| 检查时间 | {check_time} |",
        f"| 域名总数 | {total} |",
        f"| ✅ 检查成功 | {success} |",
        f"| ❌ 检查失败 | {failed} |",
        f"| 🔴 紧急（≤{URGENT_DAYS} 天） | {urgent} |",
        f"| 🟡 警告（≤{WARNING_DAYS} 天） | {warning} |",
        f"| ⚫ 已过期 | {expired_count} |",
        f"| 🟢 正常（>{WARNING_DAYS} 天） | {normal_count} |",
        "",
    ]
    return "\n".join(lines)


def generate_detail_table(results):
    """生成按紧急度排序的明细表。"""
    sorted_results = sort_results(results)

    if not sorted_results:
        return "## 明细\n\n无有效域名检查结果。\n"

    lines = [
        "## 明细（按紧急程度排序）",
        "",
        "| # | 紧急度 | 域名 | 端口 | 状态 | 颁发者 | 到期时间 | 剩余天数 | SAN 域名 |",
        "|---|--------|------|------|------|--------|---------|---------|---------|",
    ]

    for idx, r in enumerate(sorted_results, 1):
        domain = r.get("domain", "?")
        port = r.get("port", "?")
        status = r.get("status", "error")
        urgency = r.get("urgency")

        urgency_text = URGENCY_LABEL.get(urgency, "⚪ 未知")
        status_text = STATUS_LABEL.get(status, status)

        if status == "error":
            err = r.get("error", "unknown")
            err_text = ERROR_LABEL.get(err, err)
            if r.get("error_detail"):
                err_text += f"（{r['error_detail'][:40]}）"
            # 失败原因合并到状态列，一行一个域名，表格不渲染错位
            lines.append(
                f"| {idx} | {urgency_text} | `{domain}` | {port} | 检查失败：{err_text} | - | - | - | - |"
            )
        else:
            issuer = r.get("issuer", "-") or "-"
            not_after = format_datetime(r.get("not_after"))
            days = r.get("days_remaining", "?")
            san = format_san(r.get("san", []))
            chain_flag = ""
            if r.get("chain_incomplete"):
                chain_flag = " ⚠️链不完整"

            if status == "expired":
                days_text = f"**已过期 {abs(days)} 天**"
            else:
                days_text = f"{days} 天"

            lines.append(
                f"| {idx} | {urgency_text} | `{domain}` | {port} | {status_text}{chain_flag} | {issuer} | {not_after} | {days_text} | {san} |"
            )

    lines.append("")
    return "\n".join(lines)


def generate_renewal_hint(results):
    """生成续签指引提示（只在有紧急/警告/过期时才显示）。"""
    needs_renewal = [
        r for r in results
        if r.get("urgency") in ("urgent", "warning")
        or r.get("status") == "expired"
    ]

    if not needs_renewal:
        return ""

    domains_list = sorted(set(
        r["domain"] for r in needs_renewal if r.get("domain")
    ))

    lines = [
        "## ⚠️ 需续签域名清单",
        "",
        f"以下 {len(needs_renewal)} 个域名证书即将到期或已过期，请尽快处理：",
        "",
    ]
    for d in domains_list:
        lines.append(f"- `{d}`")

    lines.extend([
        "",
        "续签操作指引见参考文档 `references/renewal_guide.md`，按证书颁发平台选择对应流程。",
        "续签完成后，需将新证书部署到对应服务（Nginx/K8s Secret/CDN 等），此步骤不在本 Skill 范围内。",
        "",
    ])
    return "\n".join(lines)


def generate_report(data):
    """生成完整 Markdown 报告。"""
    results = data.get("results", [])

    sections = [
        "# SSL 证书到期巡检报告",
        "",
        f"> 生成时间：{format_datetime(datetime.now(timezone.utc).isoformat())}",
        "",
        generate_summary_section(data),
    ]

    if results:
        sections.append(generate_detail_table(results))

    renewal_hint = generate_renewal_hint(results)
    if renewal_hint:
        sections.append(renewal_hint)

    sections.extend([
        "---",
        "",
        "_本报告由 ssl-cert-monitor Skill 自动生成。如需重新检查，运行 `scripts/check_certs.py`。_",
        "",
    ])

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(
        description="SSL 证书巡检报告生成器（JSON → Markdown）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
    python generate_report.py --input check_result.json --output report.md
    python generate_report.py --input check_result.json
    python generate_report.py < check_result.json > report.md
        """,
    )
    parser.add_argument("--input", help="check_certs.py 产出的 JSON 文件路径（不指定则从 stdin 读取）")
    parser.add_argument("--output", help="输出 Markdown 文件路径（不指定则输出到 stdout）")
    args = parser.parse_args()

    # 读取 JSON
    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"[错误] 输入文件不存在：{args.input}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"[错误] JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"[错误] stdin JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)

    # 基本结构校验
    if not isinstance(data, dict) or "results" not in data:
        print("[错误] 输入 JSON 格式不符合预期（缺少 results 字段）", file=sys.stderr)
        sys.exit(1)

    # 生成报告
    report = generate_report(data)

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[完成] 报告已写入 {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
