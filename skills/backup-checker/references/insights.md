# Insights — backup-checker 长期规则库

> 由第 ⑦ 步从 growth_log 提炼的高影响、可改变默认行为的经验。
> 生效中的规则是后续迭代/新建 Skill 时的默认行为，不需重新设计。

---

## 生效中的规则

### Rule 8 · 外部 CLI 降级链设计

**规则**：当一个检查目标有多种工具可选时（如 MinIO/S3 可用 mc 或 aws-cli），设计降级链：首选工具失败（rc=127 即未安装）时自动尝试备选，两者都不可时报明确错误而非崩溃。

**原因**：用户环境不可控，有人装 mc 有人装 aws-cli，降级链让 Skill 在更多环境可用。

**模式**：
```python
rc, out, err = _run_cmd(["mc", ...])
if rc == 127:  # command not found
    return _try_aws_fallback(...)
if rc != 0:
    # maybe mc installed but not configured; try aws
    aws_res = _try_aws_fallback(...)
    if aws_res["health"] != HEALTH_ERROR:
        return aws_res
    return _result_error(...)
```

**适用场景**：任何需要调用外部 CLI 且有多种替代工具的 Skill。

---

### Rule 9 · 只读安全红线贯穿全脚本

**规则**：备份/巡检类 Skill 的所有外部调用（SSH/mc/kubectl）必须严格只读——只用 stat/ls/get 等查询命令，绝不用写入/删除/创建命令。凭据走环境变量或工具自身配置（mc alias / aws configure / kubeconfig），不硬编码。

**原因**：备份场景下误写入/误删除是不可逆的灾难。检查与备份任务必须解耦，避免巡检脚本误触发备份覆盖已有数据。

**操作**：
- SSH 调用用 `stat -c '%s %Y'` 查文件元信息，不用任何写入命令
- mc 调用用 `mc ls`，不用 `mc cp/mv/rm`
- kubectl 调用用 `kubectl get -o json --ignore-not-found`，不用 apply/delete/create
- 凭据不写进 CSV/脚本，走 `BACKUP_CHECKER_MC_ALIAS` / `BACKUP_CHECKER_S3_ENDPOINT` / `KUBECONFIG` 等环境变量

**适用场景**：任何涉及备份/配置/生产资源检查的 Skill。

---

### Rule 10 · 健康度分级要有"检查失败"态（从 backup-checker 提炼）

**规则**：巡检类 Skill 的健康度分级，除了业务状态（缺失/过期/异常/正常）外，必须单独设一级"检查失败"，区分"目标有问题"和"检查工具有问题"。

**原因**：检查失败的原因（SSH 未配免密/mc 未装/kubectl 权限不足）跟备份本身的问题是两类，混在一起会让用户误判。单独一级让用户先修工具再查目标。

**适用场景**：任何调用外部工具做巡检的 Skill（ssl-cert-monitor 不需要，因为它只调 Python 标准库无外部依赖）。
