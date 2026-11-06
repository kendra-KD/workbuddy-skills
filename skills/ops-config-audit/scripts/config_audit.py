#!/usr/bin/env python3
"""
运维配置审计器主入口。

用法：
  python config_audit.py --type nginx-upstream --nginx-conf /etc/nginx/nginx.conf
  python config_audit.py --type ssl-cert-match --cert cert.pem --domains domains.csv
  python config_audit.py --type k8s-configmap-drift --current current.yaml --expected expected.yaml
  python config_audit.py --type k8s-ingress-cert --ingress-yaml ingress.yaml --secret-yaml secret.yaml
  python config_audit.py --type multi-env-diff --files dev.conf,staging.conf,prod.conf
  python config_audit.py --list-types
"""

import argparse
import json
import sys

from nginx_audit import audit_nginx_upstream, audit_nginx_ssl_mismatch
from ssl_audit import audit_ssl_cert_match
from k8s_audit import (
    audit_k8s_configmap_drift,
    audit_k8s_secret_drift,
    audit_k8s_ingress_cert,
    audit_multi_env_diff,
    audit_k8s_resource_limits,
)


AUDIT_TYPES = {
    "nginx-upstream": {
        "name": "Nginx upstream 一致性审计",
        "handler": audit_nginx_upstream,
        "args": ["nginx_conf"],
    },
    "ssl-cert-match": {
        "name": "SSL 证书与域名匹配审计",
        "handler": audit_ssl_cert_match,
        "args": ["cert", "domains"],
    },
    "k8s-configmap-drift": {
        "name": "K8s ConfigMap 漂移审计",
        "handler": audit_k8s_configmap_drift,
        "args": ["current", "expected"],
    },
    "k8s-secret-drift": {
        "name": "K8s Secret 漂移审计",
        "handler": audit_k8s_secret_drift,
        "args": ["current", "expected"],
    },
    "k8s-ingress-cert": {
        "name": "K8s Ingress 证书匹配审计",
        "handler": audit_k8s_ingress_cert,
        "args": ["ingress_yaml", "secret_yaml"],
    },
    "multi-env-diff": {
        "name": "多环境配置差异审计",
        "handler": audit_multi_env_diff,
        "args": ["files"],
    },
    "nginx-ssl-mismatch": {
        "name": "Nginx server_name 与证书 SAN 匹配审计",
        "handler": audit_nginx_ssl_mismatch,
        "args": ["nginx_conf"],
    },
    "k8s-resource-limits": {
        "name": "K8s 工作负载资源限制审计",
        "handler": audit_k8s_resource_limits,
        "args": ["current"],
    },
}


def severity_icon(level: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": ""}.get(level, "⚪")


def print_markdown_report(audit_type: str, findings: list):
    meta = AUDIT_TYPES.get(audit_type, {})
    print(f"# {meta.get('name', '配置审计报告')}\n")
    print(f"**审计类型**: `{audit_type}`")
    print(f"**发现问题数**: {len(findings)}\n")
    if not findings:
        print("✅ 未发现明显配置风险。\n")
        return

    print("| 风险等级 | 审计项 | 位置 | 问题 | 修复建议 |")
    print("|---------|--------|------|------|---------|")
    for f in findings:
        print(
            f"| {severity_icon(f['severity'])} {f['severity'].upper()} "
            f"| {f['category']} | {f.get('loc', '-')} | {f['message']} | {f['suggestion']} |"
        )
    print()


def print_json_report(audit_type: str, findings: list):
    print(json.dumps({"audit_type": audit_type, "findings": findings}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="运维配置审计器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            ["支持类型:"] + [f"  {k}: {v['name']}" for k, v in AUDIT_TYPES.items()]
        ),
    )
    parser.add_argument("--type", choices=list(AUDIT_TYPES.keys()), help="审计类型")
    parser.add_argument("--nginx-conf", help="Nginx 配置文件或目录")
    parser.add_argument("--cert", help="证书文件路径")
    parser.add_argument("--domains", help="域名清单 CSV 或单个域名")
    parser.add_argument("--current", help="当前配置 YAML（k8s-resource-limits 时为工作负载 YAML）")
    parser.add_argument("--workload", help="工作负载 YAML（k8s-resource-limits 别名）")
    parser.add_argument("--expected", help="期望配置 YAML")
    parser.add_argument("--ingress-yaml", help="Ingress YAML 文件")
    parser.add_argument("--secret-yaml", help="Secret YAML 文件")
    parser.add_argument("--files", help="多环境配置文件，逗号分隔")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="输出格式")
    parser.add_argument("--list-types", action="store_true", help="列出支持的审计类型")

    args = parser.parse_args()

    if args.list_types:
        print("支持的审计类型:")
        for k, v in AUDIT_TYPES.items():
            print(f"  {k:20s} {v['name']}")
        return

    if not args.type:
        parser.print_help()
        sys.exit(1)

    meta = AUDIT_TYPES[args.type]
    handler = meta["handler"]
    findings = handler(args)

    if args.format == "json":
        print_json_report(args.type, findings)
    else:
        print_markdown_report(args.type, findings)


if __name__ == "__main__":
    main()
