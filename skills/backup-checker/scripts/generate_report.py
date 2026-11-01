#!/usr/bin/env python3
"""Generate a Markdown report from backup check JSON results.

Reads check_result.json (produced by check_backups.py) and writes
a Markdown table sorted by health severity (missing -> stale -> abnormal -> error -> ok).
"""

import argparse
import json
import sys
from datetime import datetime, timezone

HEALTH_LABEL = {
    "missing": "🔴 缺失",
    "stale": "🟡 过期",
    "abnormal": "🟠 异常",
    "ok": "🟢 正常",
    "error": "❌ 检查失败",
}

HEALTH_SORT = {
    "missing": 0,
    "stale": 1,
    "abnormal": 2,
    "error": 3,
    "ok": 4,
}


def _fmt_size(size_mb):
    if size_mb is None:
        return "-"
    if size_mb < 1:
        return f"{round(size_mb * 1024, 1)} KB"
    return f"{size_mb} MB"


def _fmt_ts(ts):
    if not ts:
        return "-"
    # ts is ISO string; trim to YYYY-MM-DD HH:MM
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts[:16] if isinstance(ts, str) else "-"


def generate_report(data):
    lines = []
    lines.append("# 备份健康巡检报告")
    lines.append("")
    checked_at = data.get("checked_at", "")
    lines.append(f"> 巡检时间：{_fmt_ts(checked_at)}")
    s = data.get("summary", {})
    lines.append(f"> 总计 {data.get('total', 0)} 个目标  |  "
                 f"🟢正常 {s.get('ok', 0)}  |  "
                 f"🔴缺失 {s.get('missing', 0)}  |  "
                 f"🟡过期 {s.get('stale', 0)}  |  "
                 f"🟠异常 {s.get('abnormal', 0)}  |  "
                 f"❌失败 {s.get('error', 0)}")
    lines.append("")
    lines.append("| 目标 | 类型 | 路径 | 大小 | 最后修改 | 健康度 | 说明 |")
    lines.append("|------|------|------|------|---------|--------|------|")

    results = sorted(data.get("results", []),
                     key=lambda r: HEALTH_SORT.get(r.get("health"), 99))
    for r in results:
        name = r.get("name", "")
        rtype = r.get("type", "")
        path = r.get("path", "")
        size = _fmt_size(r.get("size_mb"))
        mtime = _fmt_ts(r.get("last_modified"))
        health = HEALTH_LABEL.get(r.get("health"), r.get("health", ""))
        detail = r.get("detail", "") or "-"
        lines.append(f"| {name} | {rtype} | {path} | {size} | {mtime} | {health} | {detail} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 健康度说明")
    lines.append("")
    lines.append("- 🔴 **缺失**：备份文件/对象不存在，立即排查备份任务是否在跑")
    lines.append("- 🟡 **过期**：时间戳超过期望阈值，确认备份任务卡住或调度异常")
    lines.append("- 🟠 **异常**：存在但大小低于阈值，疑似空备份/失败备份，查备份日志")
    lines.append("- ❌ **检查失败**：检查本身出错（SSH/mc/aws-cli 未就绪或权限不足）")
    lines.append("- 🟢 **正常**：存在、未过期、大小合理")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Generate Markdown backup report")
    ap.add_argument("--input", "-i", default="check_result.json",
                    help="input JSON path (default: check_result.json)")
    ap.add_argument("--output", "-o", default="backup_report.md",
                    help="output Markdown path (default: backup_report.md)")
    args = ap.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"error: input not found: {args.input}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(2)

    report = generate_report(data)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"report written to {args.output}")


if __name__ == "__main__":
    main()
