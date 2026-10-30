#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSL Cert Monitor - 核心检查脚本
读取域名清单，查询每个域名的 SSL/TLS 证书到期情况，输出 JSON 结构化数据。

只用 Python 标准库（ssl + socket + csv + json），不依赖第三方包。
单个域名检查失败时记录错误原因并继续，不中断整体流程。

用法：
    python check_certs.py --csv assets/domains_template.csv
    python check_certs.py --domains example.com blog.example.com:8443
    python check_certs.py --csv domains.csv --output check_result.json

输出：
    JSON 文件，结构见 OUTPUT_SCHEMA 下方注释。
"""

import argparse
import base64
import csv
import json
import os
import socket
import ssl
import sys
import tempfile
from datetime import datetime, timezone

# 紧急程度阈值（天）
URGENT_DAYS = 7      # <=7 天：紧急
WARNING_DAYS = 30    # <=30 天：警告
# >30 天：正常

# 连接超时（秒）
CONNECT_TIMEOUT = 10


def parse_domain_input(raw):
    """
    解析单个域名输入，支持以下格式：
        example.com
        example.com:8443
        https://example.com
        https://example.com:8443/
        example.com/
    返回 (domain, port) 元组，port 默认 443。
    """
    raw = raw.strip()
    if not raw:
        return None, None

    # 剥离协议前缀
    if raw.startswith("https://"):
        raw = raw[len("https://"):]
    elif raw.startswith("http://"):
        raw = raw[len("http://"):]

    # 剥离路径部分
    if "/" in raw:
        raw = raw.split("/", 1)[0]

    # 解析端口
    if ":" in raw:
        parts = raw.rsplit(":", 1)
        domain = parts[0].strip()
        try:
            port = int(parts[1].strip())
        except ValueError:
            return domain, 443
    else:
        domain = raw
        port = 443

    if not domain:
        return None, None
    return domain, port


def read_domains_from_csv(csv_path):
    """
    从 CSV 文件读取域名清单。
    支持两种格式：
        1. 有表头：domain,port
        2. 无表头：每行一个域名（可带端口）
    返回 [(domain, port), ...] 列表，跳过空行和格式错误行。
    """
    domains = []
    warnings = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            # 先过滤掉注释行和空行，再交给 csv 解析
            # （csv.Sniffer 对含 # 注释的样本会报 Could not determine delimiter）
            raw_lines = f.readlines()
            filtered = [
                line for line in raw_lines
                if line.strip() and not line.strip().startswith("#")
            ]

            # 嗅探是否有表头（嗅探失败时降级为"有表头"，更安全）
            has_header = True
            if filtered:
                try:
                    sample = "".join(filtered[:5])
                    has_header = csv.Sniffer().has_header(sample)
                except csv.Error:
                    # 第一行看起来像 domain,port 表头就按有表头处理
                    first = filtered[0].strip().lower()
                    has_header = first.startswith("domain") or "port" in first

            import io
            reader = csv.reader(io.StringIO("".join(filtered)))
            for idx, row in enumerate(reader):
                if not row or all(cell.strip() == "" for cell in row):
                    continue

                # 跳过表头行
                if has_header and idx == 0:
                    continue

                # 格式1：domain,port 两列
                if len(row) >= 2:
                    domain = row[0].strip()
                    try:
                        port = int(row[1].strip()) if row[1].strip() else 443
                    except ValueError:
                        warnings.append(f"第 {idx+1} 行端口非数字，已跳过：{row}")
                        continue
                # 格式2：单列域名（可带端口）
                elif len(row) == 1:
                    domain, port = parse_domain_input(row[0])
                    if domain is None:
                        warnings.append(f"第 {idx+1} 行无法解析，已跳过：{row}")
                        continue
                else:
                    warnings.append(f"第 {idx+1} 行格式错误，已跳过：{row}")
                    continue

                if domain:
                    domains.append((domain, port))

    except FileNotFoundError:
        print(f"[错误] CSV 文件不存在：{csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 读取 CSV 失败：{e}", file=sys.stderr)
        sys.exit(1)

    for w in warnings:
        print(f"[警告] {w}", file=sys.stderr)

    return domains


def check_single_cert(domain, port, timeout=CONNECT_TIMEOUT):
    """
    检查单个域名的 SSL 证书信息。
    返回 dict，包含证书信息或错误信息。

    成功结构：
        {
            "domain": "example.com",
            "port": 443,
            "status": "ok",          # ok / expired / error
            "issuer": "Let's Encrypt",
            "subject": "example.com",
            "san": ["example.com", "www.example.com"],
            "not_before": "2026-01-01T00:00:00Z",
            "not_after": "2026-04-01T00:00:00Z",
            "days_remaining": 30,
            "urgency": "normal",      # urgent / warning / normal
            "chain_incomplete": false
        }
    失败结构：
        {
            "domain": "example.com",
            "port": 443,
            "status": "error",
            "error": "timeout",       # timeout / dns_resolve_failed / connection_refused / no_certificate / ssl_error / unknown
            "days_remaining": null,
            "urgency": null
        }
    """
    result = {
        "domain": domain,
        "port": port,
        "status": "error",
        "days_remaining": None,
        "urgency": None,
    }

    ctx = ssl.create_default_context()
    # 不验证证书链——用 get_unverified_chain() 拿原始 DER 证书后自行解析
    # 这样不依赖环境 CA 证书库（Windows 下 Python 常出现证书库缺失问题）
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                # 拿原始 DER 证书链
                chain = ssock.get_unverified_chain()
                if not chain:
                    result["status"] = "error"
                    result["error"] = "no_certificate"
                    return result

                # 取叶端证书（链的第一个），DER 转 PEM 后解码
                der_bytes = chain[0]
                pem = base64.encodebytes(der_bytes).decode("ascii")
                pem = "-----BEGIN CERTIFICATE-----\n" + pem + "-----END CERTIFICATE-----\n"

                # 写临时文件用 ssl._ssl._test_decode_cert 解析
                tmpfd, tmppath = tempfile.mkstemp(suffix=".pem")
                try:
                    with os.fdopen(tmpfd, "w") as f:
                        f.write(pem)
                    cert = ssl._ssl._test_decode_cert(tmppath)
                finally:
                    os.unlink(tmppath)

                if not cert:
                    result["status"] = "error"
                    result["error"] = "no_certificate"
                    return result

                # 检查证书链完整性（链长度 < 2 可能是不完整）
                chain_incomplete = len(chain) < 2

                # 提取到期时间
                not_after_str = cert.get("notAfter", "")
                not_after = ssl.cert_time_to_seconds(not_after_str)
                not_after_dt = datetime.fromtimestamp(not_after, tz=timezone.utc)

                # 提取生效时间
                not_before_str = cert.get("notBefore", "")
                not_before = ssl.cert_time_to_seconds(not_before_str)
                not_before_dt = datetime.fromtimestamp(not_before, tz=timezone.utc)

                # 计算剩余天数
                now = datetime.now(timezone.utc)
                days_remaining = (not_after_dt - now).days

                # 提取颁发者
                # 结构：((('countryName','US'),), (('organizationName','SSL Corp'),), (('commonName','CA'),))
                issuer_parts = cert.get("issuer", ())
                issuer = ""
                for group in issuer_parts:
                    # group 形如 (('organizationName', 'SSL Corp'),)
                    if group and isinstance(group, tuple) and len(group) >= 1:
                        inner = group[0]
                        if inner and isinstance(inner, tuple) and len(inner) >= 2:
                            key, val = inner[0], inner[1]
                            if key == "organizationName" and val:
                                issuer = val
                                break
                            if key == "commonName" and val and not issuer:
                                issuer = val
                if not issuer and issuer_parts:
                    issuer = str(issuer_parts)

                # 提取主体
                subject_parts = cert.get("subject", ())
                subject = ""
                for group in subject_parts:
                    if group and isinstance(group, tuple) and len(group) >= 1:
                        inner = group[0]
                        if inner and isinstance(inner, tuple) and len(inner) >= 2:
                            key, val = inner[0], inner[1]
                            if key == "commonName" and val:
                                subject = val
                                break
                if not subject and subject_parts:
                    subject = str(subject_parts)

                # 提取 SAN（备用域名）
                san_list = []
                for san_entry in cert.get("subjectAltName", ()):
                    if len(san_entry) >= 2 and san_entry[0] == "DNS":
                        san_list.append(san_entry[1])

                # 判断状态
                if days_remaining < 0:
                    status = "expired"
                else:
                    status = "ok"

                # 紧急程度分级
                if days_remaining <= URGENT_DAYS:
                    urgency = "urgent"
                elif days_remaining <= WARNING_DAYS:
                    urgency = "warning"
                else:
                    urgency = "normal"

                result.update({
                    "status": status,
                    "issuer": issuer,
                    "subject": subject,
                    "san": san_list,
                    "not_before": not_before_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "not_after": not_after_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "days_remaining": days_remaining,
                    "urgency": urgency,
                    "chain_incomplete": chain_incomplete,
                })

    except socket.gaierror:
        result["error"] = "dns_resolve_failed"
    except socket.timeout:
        result["error"] = "timeout"
    except ConnectionRefusedError:
        result["error"] = "connection_refused"
    except ssl.SSLError as e:
        result["error"] = "ssl_error"
        result["error_detail"] = str(e)
    except Exception as e:
        result["error"] = "unknown"
        result["error_detail"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="SSL 证书到期批量检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
    python check_certs.py --csv assets/domains_template.csv
    python check_certs.py --domains example.com blog.example.com:8443
    python check_certs.py --csv domains.csv --output result.json
        """,
    )
    parser.add_argument("--csv", help="CSV 域名清单文件路径（字段：domain,port）")
    parser.add_argument("--domains", nargs="+", help="直接列出域名（空格分隔，可带端口）")
    parser.add_argument("--output", default="check_result.json", help="输出 JSON 文件路径（默认 check_result.json）")
    args = parser.parse_args()

    # 获取域名清单
    domains = []
    if args.csv:
        domains = read_domains_from_csv(args.csv)
    elif args.domains:
        for d in args.domains:
            parsed_domain, parsed_port = parse_domain_input(d)
            if parsed_domain:
                domains.append((parsed_domain, parsed_port))
    else:
        parser.error("必须指定 --csv 或 --domains 之一")

    if not domains:
        print("[提示] 无有效域名可检查", file=sys.stderr)
        # 仍输出空 JSON 数组
        results = []
    else:
        print(f"[开始] 共 {len(domains)} 个域名待检查", file=sys.stderr)

        results = []
        for idx, (domain, port) in enumerate(domains, 1):
            print(f"[{idx}/{len(domains)}] 检查 {domain}:{port} ...", file=sys.stderr, end=" ")
            result = check_single_cert(domain, port)
            results.append(result)

            if result["status"] == "error":
                print(f"失败（{result.get('error', 'unknown')}）", file=sys.stderr)
            elif result["status"] == "expired":
                print(f"已过期", file=sys.stderr)
            else:
                days = result.get("days_remaining", "?")
                urgency = result.get("urgency", "?")
                print(f"剩余 {days} 天（{urgency}）", file=sys.stderr)

    # 输出 JSON
    output = {
        "check_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(results),
        "success": len([r for r in results if r["status"] in ("ok", "expired")]),
        "failed": len([r for r in results if r["status"] == "error"]),
        "urgent_count": len([r for r in results if r.get("urgency") == "urgent"]),
        "warning_count": len([r for r in results if r.get("urgency") == "warning"]),
        "results": results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 结果已写入 {args.output}", file=sys.stderr)
    print(f"[汇总] 共 {output['total']} 个域名：成功 {output['success']}，失败 {output['failed']}，紧急 {output['urgent_count']}，警告 {output['warning_count']}", file=sys.stderr)


if __name__ == "__main__":
    main()
