#!/usr/bin/env python3
"""Backup health checker.

Reads a CSV inventory of backup targets, checks each target's health
(existence / size / freshness), and writes structured JSON results.

Supported target types:
  - local-file : file/dir on a remote host via SSH (stat)
  - minio-s3   : objects in an S3/MinIO bucket via mc or aws-cli
  - database   : database dump file (checked as local-file with db-aware logic)
  - k8s-resource : Kubernetes resource exported as YAML (kubectl get -o yaml)

Security: read-only. No write/create/delete operations on any target.
Credentials come from environment variables, never hardcoded.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# ----- Constants -----

HEALTH_MISSING = "missing"   # backup does not exist
HEALTH_STALE = "stale"       # exists but timestamp too old
HEALTH_ABNORMAL = "abnormal"  # exists but size too small (suspected empty/failed)
HEALTH_OK = "ok"             # exists, fresh, size reasonable
HEALTH_ERROR = "error"       # check itself failed (ssh/mc not installed, perms)

HEALTH_LABEL = {
    HEALTH_MISSING: "🔴 缺失",
    HEALTH_STALE: "🟡 过期",
    HEALTH_ABNORMAL: "🟠 异常",
    HEALTH_OK: "🟢 正常",
    HEALTH_ERROR: "❌ 检查失败",
}

HEALTH_SORT_ORDER = {
    HEALTH_MISSING: 0,
    HEALTH_STALE: 1,
    HEALTH_ABNORMAL: 2,
    HEALTH_ERROR: 3,
    HEALTH_OK: 4,
}

DEFAULT_TIMEOUT = 15  # seconds for each remote command


# ----- Helpers -----

def _now():
    return datetime.now(timezone.utc)


def _run_cmd(cmd, timeout=DEFAULT_TIMEOUT):
    """Run a command, return (returncode, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def _parse_iso_or_ts(ts_str):
    """Parse a timestamp string into a datetime. Best-effort."""
    if not ts_str:
        return None
    ts_str = ts_str.strip().strip('"')
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _hours_since(dt):
    if dt is None:
        return None
    delta = _now() - dt
    return round(delta.total_seconds() / 3600, 1)


# ----- Checkers -----

def check_local_file(target):
    """Check a file on a remote host via SSH stat.

    Required env: none if host is localhost; SSH key must be set up for remote.
    Uses: ssh <host> stat -c '%s %Y' <path>  (Linux)
    """
    path = target["path"]
    host = target.get("host", "localhost")
    min_size_mb = float(target.get("expected_min_size_mb", 0))
    max_age_hours = float(target.get("expected_max_age_hours", 0))

    if host in ("localhost", "127.0.0.1", "::1", ""):
        # local stat
        try:
            st = os.stat(path)
            size_mb = round(st.st_size / (1024 * 1024), 2)
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            return _evaluate_file(path, size_mb, mtime, min_size_mb, max_age_hours)
        except FileNotFoundError:
            return _result_missing(path, "file not found locally")
        except Exception as e:
            return _result_error(path, f"local stat failed: {e}")

    # remote via ssh
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           host, f"stat -c '%s %Y' '{path}' 2>/dev/null || echo NOTFOUND"]
    rc, out, err = _run_cmd(cmd)
    if rc == 127:
        return _result_error(path, f"ssh not available: {err}")
    if rc != 0:
        return _result_error(path, f"ssh failed (rc={rc}): {err.strip()[:200]}")
    out = out.strip()
    if out == "NOTFOUND" or not out:
        return _result_missing(path, "file not found on remote host")
    parts = out.split()
    if len(parts) < 2:
        return _result_error(path, f"unexpected stat output: {out[:100]}")
    try:
        size_bytes = int(parts[0])
        mtime_ts = int(parts[1])
    except ValueError:
        return _result_error(path, f"cannot parse stat output: {out[:100]}")
    size_mb = round(size_bytes / (1024 * 1024), 2)
    mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
    return _evaluate_file(path, size_mb, mtime, min_size_mb, max_age_hours)


def check_minio_s3(target):
    """Check objects in an S3/MinIO bucket via mc or aws-cli.

    Uses mc if available, else aws-cli. Both must be pre-configured
    (mc alias set / aws configure) by the user.
    """
    bucket = target["path"]  # e.g. s3://backups/daily/
    host = target.get("host", "")  # optional: custom endpoint for mc
    max_age_hours = float(target.get("expected_max_age_hours", 24))
    min_objects = int(target.get("expected_min_objects", 1))

    # try mc first
    mc_alias = os.environ.get("BACKUP_CHECKER_MC_ALIAS", "local")
    cmd = ["mc", "ls", "--recursive", "--json", f"{mc_alias}/{bucket.lstrip('s3://')}".replace("s3://", "")]
    # simpler: mc ls --recursive <alias>/<bucket>
    cmd = ["mc", "ls", "--recursive", "--json", f"{mc_alias}/{bucket.replace('s3://', '')}"]
    rc, out, err = _run_cmd(cmd, timeout=30)
    if rc == 127:
        # try aws-cli
        return _check_minio_s3_via_aws(target, bucket, max_age_hours, min_objects)
    if rc != 0:
        # maybe mc not configured for this alias; try aws
        aws_result = _check_minio_s3_via_aws(target, bucket, max_age_hours, min_objects)
        if aws_result["health"] != HEALTH_ERROR:
            return aws_result
        return _result_error(bucket, f"mc failed (rc={rc}): {err.strip()[:200]}")

    # parse mc json lines
    objects = []
    for line in out.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            objects.append(obj)
        except json.JSONDecodeError:
            continue

    if not objects:
        return _result_missing(bucket, "no objects found in bucket/prefix")

    # find newest object
    newest = None
    newest_ts = None
    for obj in objects:
        ts_str = obj.get("lastModified") or obj.get("time")
        ts = _parse_iso_or_ts(ts_str) if isinstance(ts_str, str) else None
        if ts and (newest_ts is None or ts > newest_ts):
            newest_ts = ts
            newest = obj

    total_size = sum(int(o.get("size", 0)) for o in objects)
    size_mb = round(total_size / (1024 * 1024), 2)
    age_hours = _hours_since(newest_ts)

    return _evaluate_bucket(bucket, len(objects), size_mb, newest_ts, age_hours,
                            max_age_hours, min_objects)


def _check_minio_s3_via_aws(target, bucket, max_age_hours, min_objects):
    cmd = ["aws", "s3api", "list-objects-v2",
           "--bucket", bucket.replace("s3://", "").rstrip("/").split("/")[0],
           "--prefix", "/".join(bucket.replace("s3://", "").split("/")[1:]) or "",
           "--query", "Contents",
           "--output", "json"]
    endpoint = target.get("host") or os.environ.get("BACKUP_CHECKER_S3_ENDPOINT")
    if endpoint:
        cmd += ["--endpoint-url", endpoint]
    rc, out, err = _run_cmd(cmd, timeout=30)
    if rc == 127:
        return _result_error(bucket, "neither mc nor aws-cli installed")
    if rc != 0:
        return _result_error(bucket, f"aws-cli failed (rc={rc}): {err.strip()[:200]}")
    try:
        objects = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        return _result_error(bucket, f"cannot parse aws output: {out[:100]}")
    if not objects:
        return _result_missing(bucket, "no objects found")

    newest_ts = None
    for obj in objects:
        ts = _parse_iso_or_ts(obj.get("LastModified", ""))
        if ts and (newest_ts is None or ts > newest_ts):
            newest_ts = ts
    total_size = sum(int(o.get("Size", 0)) for o in objects)
    size_mb = round(total_size / (1024 * 1024), 2)
    age_hours = _hours_since(newest_ts)
    return _evaluate_bucket(bucket, len(objects), size_mb, newest_ts, age_hours,
                            max_age_hours, min_objects)


def check_database(target):
    """Check a database dump file.

    Reuses local-file logic but with db-aware messages.
    Supports mysql-dump (.sql.gz) and pg-dump (.dump/.sql) via file checks.
    """
    db_type = target.get("db_type", "mysql")
    result = check_local_file(target)
    if db_type == "mysql":
        result["detail"] = f"[mysql-dump] {result.get('detail', '')}"
    elif db_type == "postgres":
        result["detail"] = f"[pg-dump] {result.get('detail', '')}"
    elif db_type == "redis":
        result["detail"] = f"[redis-rdb] {result.get('detail', '')}"
    return result


def check_k8s_resource(target):
    """Check a K8s resource backup (exported YAML existence).

    Uses kubectl get <resource> <name> -o yaml to confirm resource exists.
    This checks resource existence, not a backup file per se.
    """
    resource = target["path"]  # e.g. configmap/app-config
    namespace = target.get("namespace", "")
    kubeconfig = os.environ.get("KUBECONFIG", "")

    cmd = ["kubectl", "get", resource]
    if namespace:
        cmd += ["-n", namespace]
    cmd += ["-o", "json", "--ignore-not-found"]
    rc, out, err = _run_cmd(cmd, timeout=20)
    if rc == 127:
        return _result_error(resource, "kubectl not installed")
    if rc != 0:
        return _result_error(resource, f"kubectl failed (rc={rc}): {err.strip()[:200]}")
    if not out.strip():
        return _result_missing(resource, "resource not found")
    try:
        obj = json.loads(out)
    except json.JSONDecodeError:
        return _result_error(resource, "cannot parse kubectl output")
    # resource exists; check if it has been modified recently
    creation_ts = _parse_iso_or_ts(obj.get("metadata", {}).get("creationTimestamp", ""))
    age_hours = _hours_since(creation_ts)
    max_age_hours = float(target.get("expected_max_age_hours", 0))
    # for k8s resources, max_age=0 means "don't check age" (resource may be old)
    if max_age_hours > 0 and age_hours is not None and age_hours > max_age_hours:
        return _result_stale(resource, f"resource age {age_hours}h > {max_age_hours}h",
                            size_mb=None, mtime=creation_ts)
    return _result_ok(resource, size_mb=None, mtime=creation_ts,
                      detail=f"resource exists (created {age_hours}h ago)" if age_hours else "resource exists")


# ----- Result builders -----

def _result_missing(path, detail):
    return {"health": HEALTH_MISSING, "path": path, "size_mb": None,
            "last_modified": None, "age_hours": None, "detail": detail}

def _result_stale(path, detail, size_mb, mtime):
    return {"health": HEALTH_STALE, "path": path, "size_mb": size_mb,
            "last_modified": mtime.isoformat() if mtime else None,
            "age_hours": _hours_since(mtime), "detail": detail}

def _result_abnormal(path, detail, size_mb, mtime):
    return {"health": HEALTH_ABNORMAL, "path": path, "size_mb": size_mb,
            "last_modified": mtime.isoformat() if mtime else None,
            "age_hours": _hours_since(mtime), "detail": detail}

def _result_ok(path, size_mb, mtime, detail=""):
    return {"health": HEALTH_OK, "path": path, "size_mb": size_mb,
            "last_modified": mtime.isoformat() if mtime else None,
            "age_hours": _hours_since(mtime), "detail": detail}

def _result_error(path, detail):
    return {"health": HEALTH_ERROR, "path": path, "size_mb": None,
            "last_modified": None, "age_hours": None, "detail": detail}


def _evaluate_file(path, size_mb, mtime, min_size_mb, max_age_hours):
    if min_size_mb > 0 and size_mb < min_size_mb:
        return _result_abnormal(path, f"size {size_mb}MB < threshold {min_size_mb}MB",
                               size_mb, mtime)
    age = _hours_since(mtime)
    if max_age_hours > 0 and age is not None and age > max_age_hours:
        return _result_stale(path, f"age {age}h > threshold {max_age_hours}h",
                            size_mb, mtime)
    return _result_ok(path, size_mb, mtime)


def _evaluate_bucket(bucket, count, size_mb, newest_ts, age_hours,
                     max_age_hours, min_objects):
    if count < min_objects:
        return _result_abnormal(bucket, f"object count {count} < min {min_objects}",
                               size_mb, newest_ts)
    if max_age_hours > 0 and age_hours is not None and age_hours > max_age_hours:
        return _result_stale(bucket, f"newest object age {age_hours}h > {max_age_hours}h",
                            size_mb, newest_ts)
    return _result_ok(bucket, size_mb, newest_ts,
                      detail=f"{count} objects, newest {age_hours}h ago")


# ----- CSV loading -----

def load_csv(csv_path):
    """Load backup targets from CSV. Supports # comment lines."""
    targets = []
    with open(csv_path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#") and ln.strip()]
    reader = csv.DictReader(lines)
    for row in reader:
        row = {k: (v or "").strip() for k, v in row.items()}
        if not row.get("name") or not row.get("type") or not row.get("path"):
            continue
        targets.append(row)
    return targets


# ----- Main -----

CHECKERS = {
    "local-file": check_local_file,
    "minio-s3": check_minio_s3,
    "database": check_database,
    "k8s-resource": check_k8s_resource,
}


def main():
    ap = argparse.ArgumentParser(description="Backup health checker")
    ap.add_argument("--csv", help="CSV inventory of backup targets")
    ap.add_argument("--output", "-o", default="check_result.json",
                    help="output JSON path (default: check_result.json)")
    ap.add_argument("--single", help="check a single target by name")
    ap.add_argument("--type", choices=list(CHECKERS.keys()), help="target type (with --single)")
    ap.add_argument("--path", help="target path (with --single)")
    ap.add_argument("--host", default="localhost", help="remote host (with --single)")
    ap.add_argument("--min-size", type=float, default=0, help="min size MB (with --single)")
    ap.add_argument("--max-age", type=float, default=0, help="max age hours (with --single)")
    args = ap.parse_args()

    if args.single:
        target = {
            "name": args.single,
            "type": args.type,
            "path": args.path,
            "host": args.host,
            "expected_min_size_mb": str(args.min_size),
            "expected_max_age_hours": str(args.max_age),
        }
        targets = [target]
    elif args.csv:
        try:
            targets = load_csv(args.csv)
        except FileNotFoundError:
            print(f"error: CSV not found: {args.csv}", file=sys.stderr)
            sys.exit(2)
        if not targets:
            print("error: no valid targets in CSV", file=sys.stderr)
            sys.exit(2)
    else:
        ap.error("either --csv or --single is required")

    results = []
    for t in targets:
        checker = CHECKERS.get(t["type"])
        if not checker:
            results.append({
                "name": t["name"], "type": t["type"], "path": t["path"],
                "health": HEALTH_ERROR,
                "size_mb": None, "last_modified": None, "age_hours": None,
                "detail": f"unknown type: {t['type']}",
            })
            continue
        try:
            res = checker(t)
        except Exception as e:
            res = {"health": HEALTH_ERROR, "path": t["path"], "size_mb": None,
                   "last_modified": None, "age_hours": None, "detail": f"checker crashed: {e}"}
        res["name"] = t["name"]
        res["type"] = t["type"]
        results.append(res)

    # sort by health severity
    results.sort(key=lambda r: HEALTH_SORT_ORDER.get(r["health"], 99))

    output = {
        "checked_at": _now().isoformat(),
        "total": len(results),
        "summary": {
            "missing": sum(1 for r in results if r["health"] == HEALTH_MISSING),
            "stale": sum(1 for r in results if r["health"] == HEALTH_STALE),
            "abnormal": sum(1 for r in results if r["health"] == HEALTH_ABNORMAL),
            "error": sum(1 for r in results if r["health"] == HEALTH_ERROR),
            "ok": sum(1 for r in results if r["health"] == HEALTH_OK),
        },
        "results": results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"checked {len(results)} targets -> {args.output}")
    s = output["summary"]
    print(f"summary: ok={s['ok']} missing={s['missing']} stale={s['stale']} "
          f"abnormal={s['abnormal']} error={s['error']}")


if __name__ == "__main__":
    main()
