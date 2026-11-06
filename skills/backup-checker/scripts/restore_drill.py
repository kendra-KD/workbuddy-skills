#!/usr/bin/env python3
"""Restore Drill — 备份可恢复性验证器（backup-checker 差异化模块）。

check_backups.py 只回答「备份在不在、多大、多新」，
本脚本进一步回答「这份备份到底能不能恢复」：

  1. 压缩包完整性校验（gzip / tar.gz / zip 结构，不解压落地）
  2. 内容特征校验（SQL dump 是否有合法语句、RDB 是否是 Redis 格式）
  3. 可恢复性评级（restorable / suspect / broken / unknown）
  4. 恢复命令提示（真要恢复时该敲什么）

安全：全程只读。
  - 不写磁盘、不解压落地、不连数据库、不修改任何文件
  - 深度读取受 --max-read-mb 限制，默认 200MB，超过则跳过深度校验
  - 远程主机只执行 head / gzip -t / tar -tzf 等只读命令

用法：
  python restore_drill.py --csv assets/backup_targets_template.csv
  python restore_drill.py --single db1-dump --path /data/backups/db1.sql.gz --db-type mysql
  python restore_drill.py --csv assets/backup_targets_template.csv --format json
  python restore_drill.py --csv assets/backup_targets_template.csv --max-read-mb 500
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_READ_MB = 200

VERDICT_RESTORABLE = "restorable"   # 关键校验全通过，可恢复
VERDICT_SUSPECT = "suspect"        # 有非关键项异常，恢复可能有问题
VERDICT_BROKEN = "broken"          # 关键校验失败，基本不能恢复
VERDICT_SKIPPED = "skipped"        # 文件过大或类型不支持，未做深度校验
VERDICT_NA = "not_applicable"      # 非文件型目标（S3 对象/K8s 资源），恢复演练不适用

VERDICT_LABEL = {
    VERDICT_RESTORABLE: "✅ 可恢复",
    VERDICT_SUSPECT: "🟠 存疑",
    VERDICT_BROKEN: "🔴 不可恢复",
    VERDICT_SKIPPED: "⚪ 未验证",
    VERDICT_NA: "➖ 不适用",
}

# 每个 check 的 critical 标记：critical 失败 -> broken，非 critical 失败 -> suspect
CHECK_DEFS = {
    "gzip_stream": {"label": "gzip 结构与 CRC", "critical": True},
    "tar_list": {"label": "tar 目录可读", "critical": True},
    "zip_test": {"label": "zip CRC 校验", "critical": True},
    "sql_header": {"label": "SQL dump 内容特征", "critical": True},
    "sql_gz_content": {"label": "解压后 SQL 内容特征", "critical": True},
    "redis_rdb": {"label": "Redis RDB 文件头", "critical": True},
    "etcd_db": {"label": "etcd 快照文件头", "critical": True},
    "yaml_parse": {"label": "YAML 可解析", "critical": False},
    "not_all_zero": {"label": "文件非全零", "critical": False},
    "non_empty": {"label": "文件非空", "critical": True},
}

# 扩展名 -> 要执行的检查链
EXT_CHECKS = {
    ".tar.gz": ["non_empty", "gzip_stream", "tar_list", "not_all_zero"],
    ".tgz": ["non_empty", "gzip_stream", "tar_list", "not_all_zero"],
    ".sql.gz": ["non_empty", "gzip_stream", "sql_gz_content", "not_all_zero"],
    ".dump.gz": ["non_empty", "gzip_stream", "sql_gz_content", "not_all_zero"],
    ".gz": ["non_empty", "gzip_stream", "not_all_zero"],
    ".zip": ["non_empty", "zip_test", "not_all_zero"],
    ".sql": ["non_empty", "sql_header", "not_all_zero"],
    ".dump": ["non_empty", "sql_header", "not_all_zero"],
    ".rdb": ["non_empty", "redis_rdb"],
    ".db": ["non_empty", "etcd_db", "not_all_zero"],
    ".yaml": ["non_empty", "yaml_parse"],
    ".yml": ["non_empty", "yaml_parse"],
}

# 恢复命令模板（按 db_type / 类型推断）
RESTORE_HINTS = {
    "mysql": "gunzip -c {path} | mysql -u<user> -p<pass> <database>",
    "postgres": "pg_restore -U<user> -d <database> {path}   # 或 psql -f 用于 .sql 明文",
    "redis": "systemctl stop redis\ncp {path} /var/lib/redis/dump.rdb\nchown redis:redis /var/lib/redis/dump.rdb\nsystemctl start redis",
    "mongodb": "mongorestore --gzip --archive={path} --drop",
    "clickhouse": "clickhouse-backup restore <backup-name>",
    "etcd": "etcdctl snapshot restore {path} --data-dir /var/lib/etcd-restored",
    "minio": "mc mirror <alias>/{bucket} <target-dir>",
    "k8s": "kubectl apply -f {path}   # 或 kubectl create -f",
    "files": "tar -xzf {path} -C <target-dir>",
}


# ---------- 基础工具 ----------

def _run_cmd(cmd, timeout=DEFAULT_TIMEOUT):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, b"", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, b"", f"timeout after {timeout}s"
    except Exception as e:
        return 1, b"", str(e)


def _is_local(host):
    return host in ("", "localhost", "127.0.0.1", "::1")


def _remote_run(host, shell_cmd, timeout=DEFAULT_TIMEOUT):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, shell_cmd]
    return _run_cmd(cmd, timeout)


def _read_head(path, n, host):
    """只读读取文件前 n 字节。返回 (ok, bytes_or_errmsg)。"""
    if _is_local(host):
        try:
            with open(path, "rb") as f:
                return True, f.read(n)
        except Exception as e:
            return False, str(e)
    rc, out, err = _remote_run(host, f"head -c {n} '{path}'")
    if rc != 0:
        return False, err.strip()[:200] or f"ssh rc={rc}"
    return True, out


def _file_size(path, host):
    if _is_local(host):
        try:
            return os.path.getsize(path)
        except Exception:
            return None
    rc, out, _ = _remote_run(host, f"stat -c '%s' '{path}' 2>/dev/null")
    if rc != 0:
        return None
    try:
        return int(out.decode().strip())
    except Exception:
        return None


# ---------- 单项检查 ----------

def check_non_empty(ctx):
    if not ctx["size"]:
        return {"name": "non_empty", "passed": False, "detail": "文件不存在或大小为 0"}
    return {"name": "non_empty", "passed": True, "detail": f"{ctx['size_mb']} MB"}


def check_not_all_zero(ctx):
    ok, data = _read_head(ctx["path"], 4096, ctx["host"])
    if not ok:
        return {"name": "not_all_zero", "passed": False, "detail": f"读取失败: {data}"}
    if not data:
        return {"name": "not_all_zero", "passed": False, "detail": "文件为空"}
    if data.strip(b"\x00") == b"":
        return {"name": "not_all_zero", "passed": False,
                "detail": "前 4KB 全为 0x00，疑似预分配/写入失败的坏备份"}
    return {"name": "not_all_zero", "passed": True, "detail": "前 4KB 含有效数据"}


def check_gzip_stream(ctx):
    """流式读完 gzip，触发 CRC 校验。不落地。"""
    if ctx["size_mb"] > ctx["max_read_mb"]:
        return {"name": "gzip_stream", "passed": True,
                "detail": f"跳过（{ctx['size_mb']}MB > 限制 {ctx['max_read_mb']}MB）", "skipped": True}
    if not _is_local(ctx["host"]):
        rc, _, err = _remote_run(ctx["host"], f"gzip -t '{ctx['path']}'", timeout=120)
        if rc == 0:
            return {"name": "gzip_stream", "passed": True, "detail": "gzip -t 通过（远程）"}
        return {"name": "gzip_stream", "passed": False, "detail": f"gzip -t 失败: {err[:200]}"}
    try:
        total = 0
        with gzip.open(ctx["path"], "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
        return {"name": "gzip_stream", "passed": True,
                "detail": f"CRC 校验通过，解压后 {round(total / 1048576, 2)} MB"}
    except Exception as e:
        return {"name": "gzip_stream", "passed": False, "detail": f"gzip 读取失败: {e}"}


def check_tar_list(ctx):
    if ctx["size_mb"] > ctx["max_read_mb"]:
        return {"name": "tar_list", "passed": True,
                "detail": f"跳过（{ctx['size_mb']}MB > 限制 {ctx['max_read_mb']}MB）", "skipped": True}
    if not _is_local(ctx["host"]):
        rc, out, err = _remote_run(ctx["host"], f"tar -tzf '{ctx['path']}' | head -50", timeout=120)
        if rc == 0:
            n = len(out.decode("utf-8", "replace").strip().splitlines())
            return {"name": "tar_list", "passed": True, "detail": f"列出 {n}+ 个条目（远程）"}
        return {"name": "tar_list", "passed": False, "detail": f"tar -tzf 失败: {err[:200]}"}
    try:
        with tarfile.open(ctx["path"], "r:gz") as tf:
            names = tf.getnames()
        if not names:
            return {"name": "tar_list", "passed": False, "detail": "tar 内无任何条目"}
        return {"name": "tar_list", "passed": True, "detail": f"{len(names)} 个条目，首项 {names[0]}"}
    except Exception as e:
        return {"name": "tar_list", "passed": False, "detail": f"tar 解析失败: {e}"}


def check_zip_test(ctx):
    if ctx["size_mb"] > ctx["max_read_mb"]:
        return {"name": "zip_test", "passed": True,
                "detail": f"跳过（{ctx['size_mb']}MB > 限制 {ctx['max_read_mb']}MB）", "skipped": True}
    if not _is_local(ctx["host"]):
        rc, _, err = _remote_run(ctx["host"], f"unzip -t '{ctx['path']}' >/dev/null", timeout=120)
        if rc == 0:
            return {"name": "zip_test", "passed": True, "detail": "unzip -t 通过（远程）"}
        return {"name": "zip_test", "passed": False, "detail": f"unzip -t 失败: {err[:200]}"}
    try:
        with zipfile.ZipFile(ctx["path"]) as zf:
            bad = zf.testzip()
            n = len(zf.namelist())
        if bad:
            return {"name": "zip_test", "passed": False, "detail": f"CRC 校验失败: {bad}"}
        return {"name": "zip_test", "passed": True, "detail": f"{n} 个文件 CRC 全通过"}
    except Exception as e:
        return {"name": "zip_test", "passed": False, "detail": f"zip 解析失败: {e}"}


SQL_MARKERS = [
    b"CREATE TABLE", b"INSERT INTO", b"DROP TABLE",
    b"-- MySQL dump", b"-- PostgreSQL database dump",
    b"COPY ", b"SET ", b"/*!", b"LOCK TABLES",
]


def check_sql_header(ctx):
    ok, data = _read_head(ctx["path"], 131072, ctx["host"])  # 128KB
    if not ok:
        return {"name": "sql_header", "passed": False, "detail": f"读取失败: {data}"}
    if not data:
        return {"name": "sql_header", "passed": False, "detail": "文件为空"}
    hit = [m.decode("utf-8", "replace") for m in SQL_MARKERS if m in data]
    if hit:
        return {"name": "sql_header", "passed": True,
                "detail": f"命中 SQL 特征: {', '.join(hit[:3])}"}
    return {"name": "sql_header", "passed": False,
            "detail": "前 128KB 未见任何 SQL 语句特征，疑似空 dump 或非 SQL 文件"}


def check_sql_gz_content(ctx):
    """校验 .sql.gz / .dump.gz 解压后的内容是否像真 SQL。"""
    if ctx["size_mb"] > ctx["max_read_mb"]:
        return {"name": "sql_gz_content", "passed": True,
                "detail": f"跳过（{ctx['size_mb']}MB > 限制 {ctx['max_read_mb']}MB）", "skipped": True}
    if not _is_local(ctx["host"]):
        rc, out, err = _remote_run(ctx["host"], f"gzip -dc '{ctx['path']}' 2>/dev/null | head -c 131072",
                                   timeout=120)
        if rc != 0:
            return {"name": "sql_gz_content", "passed": False, "detail": f"gzip -dc 失败: {err[:200]}"}
        data = out
    else:
        try:
            with gzip.open(ctx["path"], "rb") as f:
                data = f.read(131072)
        except Exception as e:
            return {"name": "sql_gz_content", "passed": False, "detail": f"gzip 解压失败: {e}"}

    if not data:
        return {"name": "sql_gz_content", "passed": False, "detail": "解压后内容为空——空 dump"}
    hit = [m.decode("utf-8", "replace") for m in SQL_MARKERS if m in data]
    if hit:
        return {"name": "sql_gz_content", "passed": True,
                "detail": f"解压后命中 SQL 特征: {', '.join(hit[:3])}"}
    return {"name": "sql_gz_content", "passed": False,
            "detail": "解压后前 128KB 无任何 SQL 语句特征，疑似空 dump 或非 SQL 内容"}


def check_redis_rdb(ctx):
    ok, data = _read_head(ctx["path"], 9, ctx["host"])
    if not ok:
        return {"name": "redis_rdb", "passed": False, "detail": f"读取失败: {data}"}
    if data[:5] != b"REDIS":
        return {"name": "redis_rdb", "passed": False,
                "detail": f"文件头不是 'REDIS'（实际 {data[:5]!r}），不是合法 RDB"}
    ver = data[5:9].decode("ascii", "replace")
    return {"name": "redis_rdb", "passed": True, "detail": f"RDB 版本 {ver}"}


def check_etcd_db(ctx):
    ok, data = _read_head(ctx["path"], 16, ctx["host"])
    if not ok:
        return {"name": "etcd_db", "passed": False, "detail": f"读取失败: {data}"}
    if not data or data.strip(b"\x00") == b"":
        return {"name": "etcd_db", "passed": False, "detail": "文件头全零，不是有效快照"}
    if ctx["size"] and ctx["size"] < 100 * 1024:
        return {"name": "etcd_db", "passed": False,
                "detail": f"仅 {ctx['size_mb']} MB，etcd 快照通常远大于此"}
    return {"name": "etcd_db", "passed": True,
            "detail": f"文件头有效，{ctx['size_mb']} MB（建议再用 etcdctl snapshot status 验证）"}


def check_yaml_parse(ctx):
    try:
        import yaml  # noqa: F401
    except ImportError:
        return {"name": "yaml_parse", "passed": True,
                "detail": "跳过（未安装 PyYAML）", "skipped": True}
    if not _is_local(ctx["host"]):
        return {"name": "yaml_parse", "passed": True, "detail": "跳过（远程 YAML 校验）", "skipped": True}
    try:
        import yaml
        with open(ctx["path"], "r", encoding="utf-8") as f:
            docs = [d for d in yaml.safe_load_all(f.read()) if d]
        if not docs:
            return {"name": "yaml_parse", "passed": False, "detail": "YAML 无有效文档"}
        return {"name": "yaml_parse", "passed": True, "detail": f"{len(docs)} 个 YAML 文档可解析"}
    except Exception as e:
        return {"name": "yaml_parse", "passed": False, "detail": f"YAML 解析失败: {e}"}


CHECK_FUNCS = {
    "non_empty": check_non_empty,
    "not_all_zero": check_not_all_zero,
    "gzip_stream": check_gzip_stream,
    "tar_list": check_tar_list,
    "zip_test": check_zip_test,
    "sql_header": check_sql_header,
    "sql_gz_content": check_sql_gz_content,
    "redis_rdb": check_redis_rdb,
    "etcd_db": check_etcd_db,
    "yaml_parse": check_yaml_parse,
}


# ---------- 主流程 ----------

def checks_for_path(path):
    lower = path.lower()
    # 长后缀优先匹配（.tar.gz 先于 .gz）
    for ext in (".tar.gz", ".sql.gz", ".dump.gz", ".tgz", ".zip", ".sql", ".dump",
                ".rdb", ".yaml", ".yml", ".db", ".gz"):
        if lower.endswith(ext):
            return EXT_CHECKS[ext]
    return ["non_empty", "not_all_zero"]


def restore_hint_for(target):
    db_type = (target.get("db_type") or "").lower()
    ttype = (target.get("type") or "").lower()
    path = target.get("path", "")
    if db_type in RESTORE_HINTS:
        hint = RESTORE_HINTS[db_type]
    elif ttype == "k8s-resource":
        hint = RESTORE_HINTS["k8s"]
    elif ttype == "minio-s3":
        hint = RESTORE_HINTS["minio"]
    elif path.lower().endswith((".tar.gz", ".tgz", ".zip")):
        hint = RESTORE_HINTS["files"]
    elif path.lower().endswith(".db"):
        hint = RESTORE_HINTS["etcd"]
    elif path.lower().endswith(".rdb"):
        hint = RESTORE_HINTS["redis"]
    else:
        hint = "(按实际恢复流程执行)"
    return hint.replace("{path}", path)


def drill_one(target, max_read_mb):
    path = target["path"]
    host = target.get("host") or "localhost"
    ttype = (target.get("type") or "").lower()

    # 非文件型目标：S3 对象和 K8s 资源没有本地文件可供完整性校验
    if ttype == "minio-s3" or path.startswith("s3://"):
        return {
            "name": target.get("name"), "path": path, "size_mb": 0,
            "verdict": VERDICT_NA,
            "checks": [{"name": "non_file_target", "passed": True,
                        "detail": "S3/MinIO 对象不做本地完整性校验，请用 check_backups.py 检查对象健康度"}],
            "restore_hint": restore_hint_for(target),
        }
    if ttype == "k8s-resource" and not os.path.isabs(path):
        return {
            "name": target.get("name"), "path": path, "size_mb": 0,
            "verdict": VERDICT_NA,
            "checks": [{"name": "non_file_target", "passed": True,
                        "detail": "K8s 资源是集群内对象而非备份文件，请用 kubectl 验证或导出 YAML 后再演练"}],
            "restore_hint": restore_hint_for(target),
        }

    size = _file_size(path, host)
    size_mb = round(size / 1048576, 2) if size else 0

    ctx = {"path": path, "host": host, "size": size, "size_mb": size_mb,
           "max_read_mb": max_read_mb}

    if size is None:
        return {
            "name": target.get("name"), "path": path, "verdict": VERDICT_BROKEN,
            "checks": [{"name": "non_empty", "passed": False, "detail": "文件不存在或无法 stat"}],
            "restore_hint": restore_hint_for(target),
        }

    names = checks_for_path(path)
    checks = []
    for n in names:
        fn = CHECK_FUNCS.get(n)
        if not fn:
            continue
        try:
            checks.append(fn(ctx))
        except Exception as e:
            checks.append({"name": n, "passed": False, "detail": f"检查异常: {e}"})

    # 评级
    critical_fail = False
    any_fail = False
    all_skipped = True
    for c in checks:
        if c.get("skipped"):
            continue
        all_skipped = False
        if not c["passed"]:
            any_fail = True
            if CHECK_DEFS.get(c["name"], {}).get("critical"):
                critical_fail = True

    if critical_fail:
        verdict = VERDICT_BROKEN
    elif any_fail:
        verdict = VERDICT_SUSPECT
    elif all_skipped:
        verdict = VERDICT_SKIPPED
    else:
        verdict = VERDICT_RESTORABLE

    return {
        "name": target.get("name"), "path": path,
        "size_mb": size_mb, "verdict": verdict, "checks": checks,
        "restore_hint": restore_hint_for(target),
    }


def load_csv(csv_path):
    import csv as _csv
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#") and ln.strip()]
    targets = []
    for row in _csv.DictReader(lines):
        clean = {}
        for k, v in row.items():
            if k is None:
                continue
            if isinstance(v, list):
                v = v[0] if v else ""
            clean[k] = (v or "").strip()
        if clean.get("name") and clean.get("path"):
            targets.append(clean)
    return targets


def print_markdown(results, max_read_mb):
    print("# 备份恢复演练报告\n")
    print(f"**生成时间**: {datetime.now(timezone.utc).isoformat()}")
    print(f"**目标数**: {len(results)}")
    print(f"**深度读取上限**: {max_read_mb} MB（超过则跳过完整性校验）\n")

    order = {VERDICT_BROKEN: 0, VERDICT_SUSPECT: 1, VERDICT_SKIPPED: 2,
             VERDICT_NA: 3, VERDICT_RESTORABLE: 4}
    results = sorted(results, key=lambda r: order.get(r["verdict"], 9))

    print("| 目标 | 路径 | 大小 | 可恢复性 | 关键结论 |")
    print("|------|------|------|---------|---------|")
    for r in results:
        key_detail = ""
        for c in r["checks"]:
            if not c["passed"]:
                key_detail = c["detail"]
                break
        if not key_detail:
            passed = [c for c in r["checks"] if not c.get("skipped")]
            key_detail = passed[-1]["detail"] if passed else "无有效校验"
        print(f"| {r['name']} | `{r['path']}` | {r.get('size_mb', 0)} MB "
              f"| {VERDICT_LABEL[r['verdict']]} | {key_detail} |")

    print("\n---\n")
    print("## 详细校验与恢复命令\n")
    for r in results:
        print(f"### {r['name']} · {VERDICT_LABEL[r['verdict']]}\n")
        print(f"- 路径: `{r['path']}`")
        print(f"- 大小: {r.get('size_mb', 0)} MB\n")
        print("| 检查项 | 结果 | 说明 |")
        print("|--------|------|------|")
        for c in r["checks"]:
            label = CHECK_DEFS.get(c["name"], {}).get("label", c["name"])
            mark = "⏭ 跳过" if c.get("skipped") else ("✅ 通过" if c["passed"] else "❌ 失败")
            print(f"| {label} | {mark} | {c['detail']} |")
        print("\n**恢复命令参考**（执行前务必确认目标环境，恢复会覆盖数据）：\n")
        print("```bash")
        print(r["restore_hint"])
        print("```\n")

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("---\n")
    print("## 汇总\n")
    for v in (VERDICT_RESTORABLE, VERDICT_SUSPECT, VERDICT_BROKEN,
              VERDICT_SKIPPED, VERDICT_NA):
        if counts.get(v):
            print(f"- {VERDICT_LABEL[v]}: {counts[v]}")


def main():
    ap = argparse.ArgumentParser(
        description="备份恢复演练验证器：校验备份是否真的可恢复（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python restore_drill.py --csv assets/backup_targets_template.csv\n"
               "  python restore_drill.py --single db1 --path /data/db1.sql.gz --db-type mysql\n"
               "  python restore_drill.py --csv assets/backup_targets_template.csv --format json",
    )
    ap.add_argument("--csv", help="备份清单 CSV（与 check_backups.py 同一格式）")
    ap.add_argument("--single", help="单个目标名")
    ap.add_argument("--path", help="目标路径（配合 --single）")
    ap.add_argument("--host", default="localhost", help="远程主机（配合 --single）")
    ap.add_argument("--db-type", default="", help="数据库类型 mysql/postgres/redis/mongodb/clickhouse")
    ap.add_argument("--type", default="local-file", help="目标类型（配合 --single）")
    ap.add_argument("--max-read-mb", type=float, default=DEFAULT_MAX_READ_MB,
                    help=f"深度读取上限 MB（默认 {DEFAULT_MAX_READ_MB}）")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("--output", "-o", help="输出文件（默认打印到 stdout）")
    args = ap.parse_args()

    if args.single:
        if not args.path:
            ap.error("--single 需要配合 --path 使用")
        targets = [{"name": args.single, "path": args.path, "host": args.host,
                    "db_type": args.db_type, "type": args.type}]
    elif args.csv:
        try:
            targets = load_csv(args.csv)
        except FileNotFoundError:
            print(f"error: CSV not found: {args.csv}", file=sys.stderr)
            sys.exit(2)
        if not targets:
            print("error: CSV 中没有有效目标", file=sys.stderr)
            sys.exit(2)
    else:
        ap.error("需要 --csv 或 --single")

    results = [drill_one(t, args.max_read_mb) for t in targets]

    if args.format == "json":
        out = json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(),
                          "results": results}, ensure_ascii=False, indent=2)
    else:
        import io
        buf = io.StringIO()
        _stdout = sys.stdout
        sys.stdout = buf
        print_markdown(results, args.max_read_mb)
        sys.stdout = _stdout
        out = buf.getvalue()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"restore drill report -> {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()