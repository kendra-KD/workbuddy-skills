# Insights — ssl-cert-monitor 长期规则库

> 由第 ⑦ 步从 growth_log 提炼的高影响、可改变默认行为的经验。
> 生效中的规则是后续迭代/新建 Skill 时的默认行为，不需重新设计。

---

## 生效中的规则

### Rule 1 · Python ssl 证书提取：永远用 DER 自解析

**规则**：用 Python 标准库提取 HTTPS 证书信息时，永远用 `get_unverified_chain()` 拿 DER 证书 + `ssl._ssl._test_decode_cert()` 解析，**不要**用 `getpeercert()`，**不要**依赖环境 CA 证书库。

**原因**：
- `CERT_NONE` 模式下 `getpeercert()` 返回空 dict（Python ssl 模块设计）
- `CERT_REQUIRED` 模式受环境 CA 库限制，Windows 上可能因缺失根证书而验证失败
- DER 自解析方案完全不依赖环境，任何 OS / 任何 CA 库状态都能工作

**适用场景**：任何需要用 Python 标准库提取证书信息的 Skill。

---

### Rule 2 · 打包前必须清理 __pycache__

**规则**：打 Skill zip 包前，必须清理 `scripts/__pycache__/` 目录和所有 `.pyc` 文件。

**原因**：`python -m py_compile`（语法校验）和脚本运行都会产生 `__pycache__/*.pyc`，打进 zip 后用户解压会看到垃圾文件，不专业。

**操作**：打包脚本里用 `dirs[:] = [d for d in dirs if d != '__pycache__']` 过滤。

---

### Rule 3 · 实测清单先行

**规则**：写脚本前先列实测清单（正常路径 + 失败路径 + 边界路径 + 安全路径四类），写脚本时按清单把容错逻辑一起设计进去。

**原因**：比"写完再想测什么"高效得多，且能避免遗漏关键失败路径的容错逻辑。

**模板**：
```
正常路径：N1~N5（单域名/多域名/泛域名/SAN/自定义端口）
失败路径：F1~F7（超时/DNS失败/端口未开放/无证书/已过期/格式错误/空清单）
边界路径：B1~B4（显式端口/协议前缀/尾部斜杠/超大批量）
安全路径：S1~S2（特殊字符不执行shell/证书链不完整仍提取）
```

---

### Rule 4 · Markdown 表格不能有跨行内容

**规则**：生成 Markdown 表格时，任何"额外说明"都不能用独立行塞进表格内部，必须合并到已有列或放到表格外部。

**原因**：Markdown 表格每行必须列数一致，独立说明行会导致渲染错位。

---

### Rule 5 · 广场检索要拆词

**规则**：用 `search_and_install_skills` 搜索广场时，长句整搜往往无结果，必须拆成单词逐词试，中英文并试。

**示例**：搜"证书到期检查巡检"整句无结果 → 拆成"SSL certificate monitor"+"证书到期检查"才有结果。
