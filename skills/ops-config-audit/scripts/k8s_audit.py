#!/usr/bin/env python3
"""K8s 配置漂移审计。"""

import csv
import io
import os
import re
from difflib import unified_diff


try:
    import yaml
except ImportError:
    yaml = None


# ---------- YAML 解析辅助 ----------

def _load_yaml(path: str):
    if yaml is None:
        raise RuntimeError("缺少 PyYAML，无法解析 YAML")
    with open(path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f.read()))


def _extract_configmap_data(doc):
    """从 ConfigMap YAML 中提取 data。"""
    if not isinstance(doc, dict):
        return {}
    kind = doc.get("kind", "")
    if kind != "ConfigMap":
        return {}
    return doc.get("data", {}) or {}


def _extract_secret_data(doc):
    """从 Secret YAML 中提取 data。"""
    if not isinstance(doc, dict):
        return {}
    if doc.get("kind") != "Secret":
        return {}
    return doc.get("data", {}) or {}


def _extract_ingress_tls(doc):
    """从 Ingress YAML 中提取 TLS 配置。"""
    if not isinstance(doc, dict):
        return []
    if doc.get("kind") not in ("Ingress", "IngressRoute"):
        return []
    spec = doc.get("spec", {})
    return spec.get("tls", []) or []


def _load_yaml_documents(path: str) -> dict:
    """加载单个 YAML 文件，按 name 返回字典。"""
    docs = {}
    for doc in _load_yaml(path):
        if not isinstance(doc, dict):
            continue
        name = doc.get("metadata", {}).get("name", "")
        kind = doc.get("kind", "")
        if name and kind in ("ConfigMap", "Secret", "Ingress", "Deployment",
                             "StatefulSet", "DaemonSet", "Job", "CronJob"):
            docs[f"{kind}/{name}"] = doc
    return docs


def _iter_containers(doc):
    """遍历工作负载里的所有容器（含 initContainers）。"""
    spec = doc.get("spec", {}) or {}
    template_spec = (spec.get("template", {}) or {}).get("spec", {}) or {}
    # CronJob 多一层 jobTemplate
    if doc.get("kind") == "CronJob":
        template_spec = ((spec.get("jobTemplate", {}) or {}).get("spec", {}) or {}) \
            .get("template", {}).get("spec", {}) or {}
    out = []
    for key in ("initContainers", "containers"):
        for c in template_spec.get(key) or []:
            if isinstance(c, dict):
                out.append(c)
    return out


# ---------- 审计实现 ----------

def audit_k8s_configmap_drift(args) -> list:
    current = args.current
    expected = args.expected
    if not current or not expected:
        return [{
            "severity": "high",
            "category": "k8s-configmap-drift",
            "message": "缺少 --current 或 --expected 参数",
            "suggestion": "提供当前和期望的 ConfigMap YAML 文件",
        }]

    findings = []
    current_docs = _load_yaml_documents(current)
    expected_docs = _load_yaml_documents(expected)

    for key, exp_doc in expected_docs.items():
        if key not in current_docs:
            findings.append({
                "severity": "high",
                "category": "k8s-configmap-drift",
                "message": f"期望的 {key} 在当前配置中不存在",
                "suggestion": "确认资源是否已创建，或是否审计了错误的文件",
            })
            continue

        cur_data = _extract_configmap_data(current_docs[key])
        exp_data = _extract_configmap_data(exp_doc)
        for k in set(cur_data.keys()) | set(exp_data.keys()):
            if k not in cur_data:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-configmap-drift",
                    "message": f"{key} 缺少 key `{k}`（期望存在）",
                    "suggestion": "检查是否误删除，或重新 apply 期望配置",
                })
            elif k not in exp_data:
                findings.append({
                    "severity": "low",
                    "category": "k8s-configmap-drift",
                    "message": f"{key} 多出 key `{k}`（期望不存在）",
                    "suggestion": "确认是否为预期变更，否则清理",
                })
            elif cur_data[k] != exp_data[k]:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-configmap-drift",
                    "message": f"{key} 的 `{k}` 值发生漂移",
                    "suggestion": "diff 当前值与期望值，确认后重新 apply 或回滚",
                })

    return findings


def audit_k8s_secret_drift(args) -> list:
    current = args.current
    expected = args.expected
    if not current or not expected:
        return [{
            "severity": "high",
            "category": "k8s-secret-drift",
            "message": "缺少 --current 或 --expected 参数",
            "suggestion": "提供当前和期望的 Secret YAML 文件",
        }]

    findings = []
    current_docs = _load_yaml_documents(current)
    expected_docs = _load_yaml_documents(expected)

    for key, exp_doc in expected_docs.items():
        if key not in current_docs:
            findings.append({
                "severity": "high",
                "category": "k8s-secret-drift",
                "message": f"期望的 {key} 在当前配置中不存在",
                "suggestion": "确认 secret 是否已创建，或是否审计了错误的文件",
            })
            continue

        cur_data = _extract_secret_data(current_docs[key])
        exp_data = _extract_secret_data(exp_doc)
        for k in set(cur_data.keys()) | set(exp_data.keys()):
            if k not in cur_data:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-secret-drift",
                    "message": f"{key} 缺少 key `{k}`（期望存在）",
                    "suggestion": "检查 secret 是否完整",
                })
            elif k not in exp_data:
                findings.append({
                    "severity": "low",
                    "category": "k8s-secret-drift",
                    "message": f"{key} 多出 key `{k}`（期望不存在）",
                    "suggestion": "确认是否为预期变更",
                })
            elif cur_data[k] != exp_data[k]:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-secret-drift",
                    "message": f"{key} 的 `{k}` 值发生漂移",
                    "suggestion": "diff 当前值与期望值，确认后重新 apply 或回滚",
                })

    return findings


def audit_k8s_ingress_cert(args) -> list:
    ingress_yaml = args.ingress_yaml
    secret_yaml = args.secret_yaml
    if not ingress_yaml or not secret_yaml:
        return [{
            "severity": "high",
            "category": "k8s-ingress-cert",
            "message": "缺少 --ingress-yaml 或 --secret-yaml 参数",
            "suggestion": "提供 Ingress YAML 和对应的 TLS secret YAML",
        }]

    findings = []
    ingress_docs = _load_yaml_documents(ingress_yaml)
    secret_docs = _load_yaml_documents(secret_yaml)

    for key, ing_doc in ingress_docs.items():
        if not key.startswith("Ingress/"):
            continue
        tls_list = _extract_ingress_tls(ing_doc)
        for tls in tls_list:
            secret_name = tls.get("secretName")
            hosts = tls.get("hosts", []) or []
            secret_key = f"Secret/{secret_name}"
            if secret_key not in secret_docs:
                findings.append({
                    "severity": "high",
                    "category": "k8s-ingress-cert",
                    "message": f"{key} 引用的 secret `{secret_name}` 不存在",
                    "suggestion": "创建 secret 或修正 ingress 的 secretName",
                })

    return findings


def audit_multi_env_diff(args) -> list:
    files_arg = args.files or ""
    files = [x.strip() for x in files_arg.split(",") if x.strip()]
    if len(files) < 2:
        return [{
            "severity": "high",
            "category": "multi-env-diff",
            "message": "多环境差异审计至少需要 2 个配置文件",
            "suggestion": "用 --files dev.conf,staging.conf,prod.conf 提供多个文件",
        }]

    contents = {}
    for f in files:
        if not os.path.exists(f):
            return [{
                "severity": "high",
                "category": "multi-env-diff",
                "message": f"文件不存在: {f}",
                "suggestion": "检查文件路径",
            }]
        with open(f, "r", encoding="utf-8") as fp:
            contents[f] = fp.read().splitlines()

    findings = []
    base_file = files[0]
    base_lines = contents[base_file]

    for other_file in files[1:]:
        diff = list(unified_diff(base_lines, contents[other_file], fromfile=base_file, tofile=other_file, lineterm=""))
        if diff:
            findings.append({
                "severity": "medium",
                "category": "multi-env-diff",
                "message": f"`{base_file}` 与 `{other_file}` 存在 {len(diff)} 行差异",
                "suggestion": "逐条确认差异是否为环境相关配置，避免 prod 配置漂移",
            })

    return findings


def audit_k8s_resource_limits(args) -> list:
    """检查工作负载是否设置 resources.requests/limits。

    检查项：
      - 缺 limits（全部缺失 → 高；仅缺 memory 或 cpu → 中）
      - 缺 requests（中）
      - limits < requests（高，会被 API Server 拒绝或行为异常）
      - 未设 memory limit（中，容易引发节点 OOM）
      - QoS 等级为 BestEffort（高，最先被驱逐）
    """
    path = args.current or args.workload
    if not path:
        return [{
            "severity": "high",
            "category": "k8s-resource-limits",
            "message": "缺少 --current 或 --workload 参数",
            "suggestion": "提供 Deployment/StatefulSet/DaemonSet 的 YAML 文件路径",
        }]
    if not os.path.exists(path):
        return [{
            "severity": "high",
            "category": "k8s-resource-limits",
            "message": f"文件不存在: {path}",
            "suggestion": "检查路径是否正确",
        }]

    try:
        docs = _load_yaml_documents(path)
    except Exception as e:
        return [{
            "severity": "high",
            "category": "k8s-resource-limits",
            "message": f"YAML 解析失败: {e}",
            "suggestion": "确认文件是合法 YAML，且 PyYAML 已安装",
        }]

    workload_kinds = ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob")
    findings = []

    for key, doc in docs.items():
        kind = doc.get("kind", "")
        if kind not in workload_kinds:
            continue

        containers = _iter_containers(doc)
        if not containers:
            continue

        for c in containers:
            cname = c.get("name", "<unnamed>")
            res = c.get("resources", {}) or {}
            requests = res.get("requests", {}) or {}
            limits = res.get("limits", {}) or {}

            if not requests and not limits:
                findings.append({
                    "severity": "high",
                    "category": "k8s-resource-limits",
                    "loc": f"{key}/{cname}",
                    "message": f"{key} 容器 `{cname}` 未设置任何 resources（QoS=BestEffort，最易被驱逐）",
                    "suggestion": "至少设置 requests.cpu/memory 和 limits.memory，推荐 QoS=Burstable 或 Guaranteed",
                })
                continue

            if not limits:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-resource-limits",
                    "loc": f"{key}/{cname}",
                    "message": f"{key} 容器 `{cname}` 只设了 requests，未设 limits",
                    "suggestion": "补充 limits，尤其是 limits.memory，避免单容器吃满节点内存触发 OOM",
                })
            elif "memory" not in limits:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-resource-limits",
                    "loc": f"{key}/{cname}",
                    "message": f"{key} 容器 `{cname}` 未设置 limits.memory",
                    "suggestion": "设置 limits.memory，否则容器内存可无限增长直到节点 OOM",
                })

            if not requests:
                findings.append({
                    "severity": "medium",
                    "category": "k8s-resource-limits",
                    "loc": f"{key}/{cname}",
                    "message": f"{key} 容器 `{cname}` 未设置 requests",
                    "suggestion": "设置 requests 让调度器能正确评估节点资源，避免超卖导致争抢",
                })

            # limits < requests 是非法配置
            for rk in ("cpu", "memory"):
                if rk in requests and rk in limits:
                    rv = _parse_quantity(requests[rk])
                    lv = _parse_quantity(limits[rk])
                    if rv is not None and lv is not None and lv < rv:
                        findings.append({
                            "severity": "high",
                            "category": "k8s-resource-limits",
                            "loc": f"{key}/{cname}",
                            "message": f"{key} 容器 `{cname}` 的 limits.{rk}({limits[rk]}) < requests.{rk}({requests[rk]})",
                            "suggestion": "limits 必须 ≥ requests，否则 API Server 会拒绝或 Pod 行为异常",
                        })

    return findings


def _parse_quantity(v):
    """把 K8s 资源值解析为数值（CPU 为核数，内存为字节数近似）。"""
    if v is None:
        return None
    s = str(v).strip()
    try:
        if s.endswith("m"):
            return float(s[:-1]) / 1000.0
        if s.endswith("Mi"):
            return float(s[:-2]) * 1024 ** 2
        if s.endswith("Gi"):
            return float(s[:-2]) * 1024 ** 3
        if s.endswith("Ki"):
            return float(s[:-2]) * 1024
        if s.endswith("M"):
            return float(s[:-1]) * 1000 ** 2
        if s.endswith("G"):
            return float(s[:-1]) * 1000 ** 3
        return float(s)
    except (ValueError, TypeError):
        return None
