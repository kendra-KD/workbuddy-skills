#!/usr/bin/env python3
"""
Runbook Matcher — 故障特征匹配预置 runbook 并输出结构化排查报告。

用法：
  python runbook_matcher.py 502                      # 关键词匹配
  python runbook_matcher.py "pod crashloopbackoff"   # 多词匹配
  echo "生产环境 502 了" | python runbook_matcher.py  # stdin 自然语言匹配
  python runbook_matcher.py --list                    # 列出所有 runbook
  python runbook_matcher.py --detail http-502         # 查看单个完整 runbook
  python runbook_matcher.py 502 --format json         # JSON 输出
"""

import argparse
import json
import os
import sys

# 同目录导入 runbook_lib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runbook_lib import RUNBOOKS, list_runbooks, get_runbook, match_runbook, match_runbooks_topn


def generate_markdown(rb):
    """把 runbook dict 渲染成 Markdown 排查报告。"""
    lines = []
    lines.append(f"# {rb['title']}\n")
    lines.append(f"**Runbook ID**: `{rb['id']}`\n")
    lines.append(f"**匹配关键词**: {', '.join(rb['keywords'])}\n")
    lines.append("---\n")
    lines.append("## 故障概述\n")
    lines.append(rb["summary"] + "\n")
    lines.append("---\n")
    lines.append("## 根因假设树（按概率排序）\n")
    lines.append("| # | 可能原因 | 验证方法 | 概率 |")
    lines.append("|---|---------|---------|------|")
    for i, rc in enumerate(rb["root_causes"], 1):
        prob_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(rc["probability"], "")
        lines.append(f"| {i} | {rc['cause']} | {rc['verify']} | {prob_icon} {rc['probability']} |")
    lines.append("")
    lines.append("> 按概率从高到低逐个验证，验证完一个排除后再验证下一个。\n")
    lines.append("---\n")
    lines.append("## 排查步骤\n")
    for i, step in enumerate(rb["steps"], 1):
        lines.append(f"### Step {i} · {step['action']}\n")
        lines.append("```bash")
        lines.append(step["command"])
        lines.append("```\n")
        lines.append(f"**预期输出**: {step['expected']}\n")
        lines.append(f"**判断**: {step['judgment']}\n")
    lines.append("---\n")
    lines.append("## 验证故障是否解决\n")
    lines.append(f"{rb['verify']}\n")
    lines.append("---\n")
    lines.append("## 回退方案\n")
    lines.append(f"如果排查过程中的操作产生了副作用，回退方法：\n\n{rb['rollback']}\n")
    lines.append("---\n")
    lines.append("\n> 📌 **运维工具链**：发现问题(ssl-cert-monitor) → 上报问题(issue-report-formatter) → 解决问题(runbook-generator)\n")
    lines.append("> 💰 本 Skill 免费使用。如需定制专属 runbook 或运维代维服务，公众号「不宕机日常」联系。\n")
    return "\n".join(lines)


def generate_json(rb):
    """把 runbook dict 输出为 JSON（无变现引导，保持数据干净）。"""
    return json.dumps(rb, ensure_ascii=False, indent=2)


def generate_no_match_markdown(query):
    """未匹配到 runbook 时的通用排查框架 + 最接近的推荐。"""
    lines = []
    lines.append(f"# 未找到匹配的 Runbook\n")
    lines.append(f"**输入**: `{query}`\n")
    lines.append("---\n")
    # 推荐最接近的 N 个
    topn = match_runbooks_topn(query, n=3)
    if topn:
        lines.append("## 最接近的 Runbook 推荐\n")
        lines.append("虽然没有精确匹配，但以下 runbook 与你的描述最相关，可以先看看：\n")
        for rb, score in topn:
            lines.append(f"### {rb['title']}（`{rb['id']}`，匹配度 {score}）")
            lines.append(f"- 关键词: {', '.join(rb['keywords'])}")
            lines.append(f"- 概述: {rb['summary'][:80]}...")
            lines.append(f"- 查看: `python runbook_matcher.py --detail {rb['id']}`\n")
        lines.append("---\n")
    lines.append("## 通用排查框架\n")
    lines.append("以下通用框架可帮助结构化排查：\n")
    lines.append("### Step 1 · 收集信息\n")
    lines.append("- 完整报错信息（截图或文本）\n")
    lines.append("- 发生时间、影响范围\n")
    lines.append("- 环境信息（集群/命名空间/服务名）\n")
    lines.append("- 最近变更（是否刚部署/改配置）\n")
    lines.append("### Step 2 · 分层排查\n")
    lines.append("- **网络层**：telnet/tcping 确认连通性\n")
    lines.append("- **服务层**：kubectl get pod / ps 确认服务存活\n")
    lines.append("- **日志层**：kubectl logs / journalctl 查看错误日志\n")
    lines.append("- **资源层**：kubectl top / df -h / free -m 确认资源充足\n")
    lines.append("### Step 3 · 上报问题\n")
    lines.append("如需上报给团队，使用 `issue-report-formatter` Skill 把信息整理成标准报告。\n")
    lines.append("---\n")
    lines.append("## 全部可用 Runbook 列表\n")
    lines.append("以下是当前内置的全部 runbook：\n")
    for rb in list_runbooks():
        lines.append(f"- `{rb['id']}` — {rb['title']}（关键词: {', '.join(rb['keywords'])}）")
    lines.append("\n用 `python runbook_matcher.py --detail <id>` 查看完整内容。\n")
    lines.append("---\n")
    lines.append("> 💰 如需把这个故障的排查经验固化成新 runbook，公众号「不宕机日常」联系。\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="运维故障 Runbook 匹配器。输入故障特征，输出结构化排查步骤。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python runbook_matcher.py 502\n"
               "  python runbook_matcher.py 'pod crashloopbackoff'\n"
               "  echo '生产 502 了' | python runbook_matcher.py\n"
               "  python runbook_matcher.py --list\n"
               "  python runbook_matcher.py --detail http-502\n"
               "  python runbook_matcher.py 502 --format json"
    )
    parser.add_argument("query", nargs="?", default=None, help="故障关键词或描述")
    parser.add_argument("--list", action="store_true", help="列出所有可用 runbook")
    parser.add_argument("--detail", metavar="ID", default=None, help="查看指定 runbook 完整内容")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="输出格式（默认 markdown）")
    args = parser.parse_args()

    # --list 模式
    if args.list:
        data = list_runbooks()
        if args.format == "json":
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"共 {len(data)} 个可用 Runbook：\n")
            for rb in data:
                print(f"  {rb['id']:25s}  {rb['title']}")
                print(f"  {'':25s}  关键词: {', '.join(rb['keywords'])}\n")
            print("用法: python runbook_matcher.py <关键词> 或 --detail <id>")
        return

    # --detail 模式
    if args.detail:
        rb = get_runbook(args.detail)
        if not rb:
            print(f"未找到 ID 为 `{args.detail}` 的 runbook。用 --list 查看可用列表。", file=sys.stderr)
            sys.exit(1)
        if args.format == "json":
            print(generate_json(rb))
        else:
            print(generate_markdown(rb))
        return

    # 匹配模式
    query = args.query
    if not query and not sys.stdin.isatty():
        query = sys.stdin.read().strip()

    if not query:
        parser.print_help()
        return

    rb = match_runbook(query)
    if not rb:
        if args.format == "json":
            print(json.dumps({"matched": False, "query": query, "available": list_runbooks()}, ensure_ascii=False, indent=2))
        else:
            print(generate_no_match_markdown(query))
        return

    if args.format == "json":
        output = {"matched": True, "query": query, "runbook": rb}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(generate_markdown(rb))


if __name__ == "__main__":
    main()
