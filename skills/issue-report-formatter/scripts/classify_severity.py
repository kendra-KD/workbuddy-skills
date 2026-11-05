#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Severity Classifier · 紧急度分级独立工具

可独立使用，也可被 format_report.py 调用。
读取一段故障描述，输出紧急度级别 + 分级依据。

使用示例：
  echo "生产环境 app-service 502 service_unavailable" | python classify_severity.py
  python classify_severity.py --text "测试环境 404 not found"
"""

import argparse
import json
import sys


# 紧急关键词（权重高）
URGENT_KEYWORDS = [
    "502", "503", "504", "500",
    "宕机", "不可用", "service_unavailable",
    "connection refused", "timeout", "超时",
    "数据丢失", "数据损坏", "oom", "killed",
]

# 重要关键词（权重中）
IMPORTANT_KEYWORDS = [
    "404", "403", "401",
    "异常", "失败", "报错", "error", "failed", "exception",
    "慢", "卡", "延迟",
]

# 普通关键词（权重低）
NORMAL_KEYWORDS = [
    "咨询", "建议", "优化", "文档", "问题", "请问", "如何",
    "能否", "可以吗", "想了解",
]

# 环境权重
PROD_ENV = ["生产", "prod", "production"]
NON_PROD_ENV = ["测试", "test", "开发", "dev", "预发", "staging"]


def classify(text: str) -> dict:
    """
    分级逻辑：
    1. 生产环境 + 核心服务不可用 → 紧急
    2. 生产环境 + 部分功能异常 → 重要
    3. 非生产环境 + 核心服务不可用 → 重要
    4. 非生产环境 + 部分功能异常 → 普通
    5. 仅咨询/优化 → 普通
    """
    text_lower = text.lower()

    is_prod = any(env in text_lower for env in PROD_ENV)
    is_non_prod = any(env in text_lower for env in NON_PROD_ENV)
    urgent_hits = sum(1 for k in URGENT_KEYWORDS if k in text_lower)
    important_hits = sum(1 for k in IMPORTANT_KEYWORDS if k in text_lower)
    normal_hits = sum(1 for k in NORMAL_KEYWORDS if k in text_lower)

    # 判定逻辑
    if is_prod:
        if urgent_hits >= 2:
            level, label, reason = "urgent", "🔴 紧急", "生产环境 + 核心服务异常（5xx/宕机/超时）"
        elif urgent_hits >= 1 or important_hits >= 1:
            level, label, reason = "important", "🟡 重要", "生产环境 + 部分功能异常"
        else:
            level, label, reason = "normal", "🟢 普通", "生产环境但未匹配异常关键词，请人工复核"
    elif is_non_prod:
        if urgent_hits >= 2:
            level, label, reason = "important", "🟡 重要", "非生产环境但核心服务异常"
        elif important_hits >= 1:
            level, label, reason = "normal", "🟢 普通", "非生产环境 + 部分功能异常"
        else:
            level, label, reason = "normal", "🟢 普通", "非生产环境 + 咨询/优化类"
    else:
        # 未明确环境
        if urgent_hits >= 2:
            level, label, reason = "important", "🟡 重要", "未明确环境但核心服务异常，建议按重要处理"
        elif normal_hits >= 2 and urgent_hits == 0:
            level, label, reason = "normal", "🟢 普通", "咨询/优化类"
        elif important_hits >= 1:
            level, label, reason = "normal", "🟢 普通", "部分功能异常，未明确环境"
        else:
            level, label, reason = "normal", "🟢 普通", "未匹配关键词，默认普通"

    return {
        "level": level,
        "label": label,
        "reason": reason,
        "matched_urgent": urgent_hits,
        "matched_important": important_hits,
        "matched_normal": normal_hits,
        "is_prod": is_prod,
        "is_non_prod": is_non_prod,
    }


def main():
    parser = argparse.ArgumentParser(description="紧急度分级工具")
    parser.add_argument("--text", help="故障描述文本（不传则从 stdin 读取）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    text = args.text if args.text else sys.stdin.read().strip()
    if not text:
        print("[错误] 请提供故障描述", file=sys.stderr)
        sys.exit(1)

    result = classify(text)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"紧急度：{result['label']}")
        print(f"分级依据：{result['reason']}")
        print(f"（自动分级，请人工复核）")
        print(f"\n关键词命中：紧急={result['matched_urgent']} 重要={result['matched_important']} 普通={result['matched_normal']}")
        print(f"环境判定：生产={result['is_prod']} 非生产={result['is_non_prod']}")


if __name__ == "__main__":
    main()
