#!/usr/bin/env python3
"""Nginx 配置 upstream 一致性审计。"""

import os
import re


def _parse_nginx_conf(path: str) -> dict:
    """解析 nginx 配置文件，返回 upstream 和 server_name/proxy_pass 信息。"""
    upstreams = {}
    servers = []

    def parse_file(p):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def extract(content):
        # upstream 块
        for m in re.finditer(r"upstream\s+(\S+)\s*\{([^}]+)\}", content, re.S):
            name = m.group(1)
            body = m.group(2)
            servers_list = re.findall(r"server\s+(\S+)", body)
            upstreams[name] = servers_list

        # server 块
        for m in re.finditer(r"server\s*\{([^}]+)\}", content, re.S):
            body = m.group(1)
            server_names = re.findall(r"server_name\s+([^;]+);", body)
            proxy_passes = re.findall(r"proxy_pass\s+([^;]+);", body)
            listen_ports = re.findall(r"listen\s+([^;]+);", body)
            ssl_cert = re.findall(r"ssl_certificate\s+([^;]+);", body)
            ssl_key = re.findall(r"ssl_certificate_key\s+([^;]+);", body)
            servers.append({
                "server_name": server_names[0].split() if server_names else [],
                "listen": listen_ports[0] if listen_ports else "",
                "proxy_pass": proxy_passes,
                "ssl_certificate": ssl_cert[0].strip() if ssl_cert else "",
                "ssl_certificate_key": ssl_key[0].strip() if ssl_key else "",
            })

    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith((".conf", ".nginx")):
                    try:
                        extract(parse_file(os.path.join(root, f)))
                    except Exception:
                        pass
    else:
        extract(parse_file(path))

    return {"upstreams": upstreams, "servers": servers}


def audit_nginx_upstream(args) -> list:
    conf = args.nginx_conf or "/etc/nginx/nginx.conf"
    if not os.path.exists(conf):
        return [{
            "severity": "high",
            "category": "nginx-upstream",
            "message": f"配置文件不存在: {conf}",
            "suggestion": "检查路径是否正确，或手动执行 `nginx -t` 验证配置",
        }]

    data = _parse_nginx_conf(conf)
    findings = []
    upstream_names = set(data["upstreams"].keys())

    for server in data["servers"]:
        for pp in server.get("proxy_pass", []):
            # proxy_pass http://backend-api/xxx;
            m = re.match(r"https?://([^/]+)", pp)
            if not m:
                continue
            upstream_name = m.group(1).split(":")[0]
            if upstream_name not in upstream_names:
                findings.append({
                    "severity": "high",
                    "category": "nginx-upstream",
                    "message": f"proxy_pass `{pp}` 指向的 upstream `{upstream_name}` 未在配置中定义",
                    "suggestion": "检查 upstream 块是否缺失，或 proxy_pass 指向的 host 是否应写为 IP:port",
                })

    # 检查是否有 upstream 没有 server 使用
    referenced = set()
    for server in data["servers"]:
        for pp in server.get("proxy_pass", []):
            m = re.match(r"https?://([^/]+)", pp)
            if m:
                referenced.add(m.group(1).split(":")[0])

    for name in upstream_names - referenced:
        findings.append({
            "severity": "low",
            "category": "nginx-upstream",
            "message": f"upstream `{name}` 已定义但未被任何 server/proxy_pass 引用",
            "suggestion": "确认是否为遗留配置，必要时清理以减少维护负担",
        })

    return findings


def audit_nginx_ssl_mismatch(args) -> list:
    """检查 Nginx 各 server 块的 server_name 是否被其引用的证书 SAN 覆盖。"""
    conf = args.nginx_conf or "/etc/nginx/nginx.conf"
    if not os.path.exists(conf):
        return [{
            "severity": "high",
            "category": "nginx-ssl-mismatch",
            "message": f"配置文件不存在: {conf}",
            "suggestion": "检查路径是否正确",
        }]

    # 复用 ssl_audit 的证书解析能力
    from ssl_audit import _extract_cert_sans, _domain_match

    data = _parse_nginx_conf(conf)
    findings = []

    for server in data["servers"]:
        names = [n for n in server.get("server_name", []) if n and n != "_"]
        cert_path = server.get("ssl_certificate", "")

        if not names:
            continue

        if not cert_path:
            # 有 server_name 但不是 HTTPS server（未配证书），只在监听 443 时告警
            if "443" in server.get("listen", ""):
                findings.append({
                    "severity": "medium",
                    "category": "nginx-ssl-mismatch",
                    "message": f"server_name `{', '.join(names)}` 监听 443 但未配置 ssl_certificate",
                    "suggestion": "为该 server 块补充 ssl_certificate / ssl_certificate_key，或确认是否应监听 80",
                })
            continue

        if not os.path.exists(cert_path):
            findings.append({
                "severity": "high",
                "category": "nginx-ssl-mismatch",
                "message": f"server_name `{', '.join(names)}` 引用的证书文件不存在: {cert_path}",
                "suggestion": "检查证书路径是否正确，或证书是否已过期被清理",
            })
            continue

        cn, sans = _extract_cert_sans(cert_path)
        if cn is None:
            findings.append({
                "severity": "medium",
                "category": "nginx-ssl-mismatch",
                "message": f"无法解析证书 {cert_path}（openssl 不可用或非 PEM 格式）",
                "suggestion": "确认 openssl 已安装且证书为 PEM 格式",
            })
            continue

        for name in names:
            if name.startswith("*."):
                continue  # 通配符 server_name 跳过
            if not _domain_match(name, sans):
                findings.append({
                    "severity": "high",
                    "category": "nginx-ssl-mismatch",
                    "message": f"server_name `{name}` 未被证书覆盖（CN={cn}, SAN={sans}）",
                    "suggestion": f"为该域名重新申请包含 `{name}` 的证书，或从该 server 块移除",
                })

        # 检查证书与私钥是否成对
        key_path = server.get("ssl_certificate_key", "")
        if key_path and os.path.exists(key_path):
            if not _cert_key_match(cert_path, key_path):
                findings.append({
                    "severity": "high",
                    "category": "nginx-ssl-mismatch",
                    "message": f"证书与私钥不匹配（{cert_path} vs {key_path}）",
                    "suggestion": "重新确认证书和私钥是否为同一次申请产出的配对文件，不匹配会导致 nginx 启动失败",
                })

    return findings


def _cert_key_match(cert_path: str, key_path: str) -> bool:
    """比对证书和私钥的 modulus 是否一致。"""
    import subprocess

    def _modulus(kind, path):
        try:
            out = subprocess.check_output(
                ["openssl", "x509" if kind == "cert" else "rsa", "-in", path,
                 "-noout", "-modulus"],
                stderr=subprocess.DEVNULL, text=True,
            )
            return out.strip()
        except Exception:
            return None

    c = _modulus("cert", cert_path)
    k = _modulus("key", key_path)
    if c is None or k is None:
        return True  # 无法判定时不误报
    return c == k
