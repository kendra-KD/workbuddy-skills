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
            servers.append({
                "server_name": server_names[0].split() if server_names else [],
                "listen": listen_ports[0] if listen_ports else "",
                "proxy_pass": proxy_passes,
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
