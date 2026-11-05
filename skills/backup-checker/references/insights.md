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

---

### Rule 11 · 数据驱动迭代优先级（从 v1.1 扩模板提炼）

**规则**：多 Skill 矩阵运营时，迭代优先级由下载数据增速决定，而非凭感觉。增速最快的 skill 优先做深度迭代（扩模板/体验优化），比做新 skill 投入产出比高。

**原因**：增速快 = 真实需求被低估 = 顺势放大能带来更多下载。做新 skill 是从 0 攒下载，做深度迭代是给已有需求加杠杆。

**操作**：定期复测各 skill 下载量，算增速（%），优先给增速 Top 1 做扩模板/体验迭代。backup-checker v1.0→v1.1 就是这个判断（+160% 增速 → 优先扩模板）。

**适用场景**：任何运营多 Skill 产品矩阵的场景。

---

### Rule 12 · 模板扩容不改代码的条件（从 v1.1 提炼）

**规则**：当 Skill 的模板本质是 CSV/配置参数化（模板内容通过 expected_* 字段传入，不写进代码数据结构）时，扩模板只需改文档+CSV 示例，不碰核心脚本。

**判断标准**：新增模板是否复用已有的 type 检查器？
- 是 → 只改 references 文档 + CSV 示例 + SKILL.md 清单表，不改代码（backup-checker v1.1）
- 否（需新增检查器）→ 需改代码，走完整实测流程（runbook v1.1 那种改 runbook_lib.py）

**原因**：区分这两类情况能避免过度测试。纯文档级改动不需要重跑脚本功能测试，只需验证文档准确性。

**适用场景**：任何采用"CSV 参数化模板"设计的 Skill。
