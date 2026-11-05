#!/usr/bin/env python3
"""SSL 证书与域名匹配审计。"""

import csv
import os
import re
import subprocess
from urllib.parse import urlparse


def _extract_cert_sans(cert_path: str):
    """用 openssl 提取证书的 CN 和 SAN。"""
    try:
        output = subprocess.check_output(
            ["openssl", "x509", "-in", cert_path, "-noout", "-text"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, []

    cn_match = re.search(r"Subject:.*?CN\s*=\s*([^\n,]+)", output)
    cn = cn_match.group(1).strip() if cn_match else ""

    san_match = re.search(r"X509v3 Subject Alternative Name:\s*\n\s+([^\n]+)", output)
    sans = []
    if san_match:
        sans = [x.strip() for x in san_match.group(1).split(",")]
        sans = [x.replace("DNS:", "").replace("IP:", "").strip() for x in sans]

    return cn, sans


def _domain_match(domain: str, sans: list) -> bool:
    domain = domain.strip().lower()
    for san in sans:
        san = san.lower().strip()
        if san == domain:
            return True
        if san.startswith("*.") and domain.endswith(san.lstrip("*")):
            return True
    return False


def _load_domains(domains_arg: str):
    if os.path.exists(domains_arg):
        with open(domains_arg, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(filter(lambda line: not line.startswith("#"), f))
            return [row[0].strip() for row in reader if row and row[0].strip()]
    return [x.strip() for x in domains_arg.split(",") if x.strip()]


def audit_ssl_cert_match(args) -> list:
    cert = args.cert
    domains = _load_domains(args.domains or "")

    if not cert or not domains:
        return [{
            "severity": "high",
            "category": "ssl-cert-match",
            "message": "缺少 --cert 或 --domains 参数",
            "suggestion": "提供证书文件和域名清单，例如：--cert cert.pem --domains example.com,www.example.com",
        }]

    if not os.path.exists(cert):
        return [{
            "severity": "high",
            "category": "ssl-cert-match",
            "message": f"证书文件不存在: {cert}",
            "suggestion": "检查证书路径是否正确",
        }]

    cn, sans = _extract_cert_sans(cert)
    if cn is None:
        return [{
            "severity": "high",
            "category": "ssl-cert-match",
            "message": f"无法解析证书: {cert}（openssl 不可用或证书格式错误）",
            "suggestion": "确保证书是 PEM 格式，且 openssl 已安装",
        }]

    findings = []
    for domain in domains:
        if not _domain_match(domain, sans):
            findings.append({
                "severity": "high",
                "category": "ssl-cert-match",
                "message": f"证书 SAN 未覆盖域名 `{domain}`（CN={cn}, SAN={sans})",
                "suggestion": "重新申请或更新证书，确保证书 SAN 包含所有需要服务的域名",
            })

    if not findings:
        return [{
            "severity": "low",
            "category": "ssl-cert-match",
            "message": f"所有 {len(domains)} 个域名均被证书覆盖（CN={cn})",
            "suggestion": "无需修复",
        }]

    return findings
