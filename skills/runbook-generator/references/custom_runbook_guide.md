# 自定义 Runbook 接入指南

> 本 Skill 内置 10 个通用运维故障 runbook。如果你有团队专属的排查经验，可以接入自定义 runbook。

---

## 接入方式

### 方式一：修改 runbook_lib.py（推荐）

在 `scripts/runbook_lib.py` 的 `RUNBOOKS` 列表中追加新 runbook 字典。

**结构模板**：

```python
{
    "id": "your-custom-id",           # 唯一 ID，小写+连字符
    "title": "故障标题",
    "keywords": ["关键词1", "关键词2", "keyword3"],  # 匹配关键词，越多越好
    "summary": "故障概述，什么情况、常见根因。",
    "root_causes": [                   # 根因假设树，按概率排序
        {"cause": "原因1", "verify": "怎么验证", "probability": "高"},
        {"cause": "原因2", "verify": "怎么验证", "probability": "中"},
    ],
    "steps": [                         # 排查步骤，按顺序
        {
            "action": "这一步做什么",
            "command": "# bash 命令\n具体命令",
            "expected": "预期输出",
            "judgment": "根据输出怎么判断",
        },
    ],
    "verify": "如何确认故障已解决。",
    "rollback": "如果操作有副作用，怎么回退。",
}
```

### 方式二：JSON 外部加载（规划中）

未来版本将支持从 `references/custom_runbooks/` 目录加载 JSON 格式的自定义 runbook，无需改代码。

---

## 自定义 Runbook 编写原则

### 1. 关键词要覆盖中英文

用户可能输入中文也可能输入英文，关键词都要包含：
```python
"keywords": ["502", "bad gateway", "网关错误", "502 bad gateway"]
```

### 2. 根因假设树按概率排序

把最常见的根因放前面，让用户先验证高概率原因：
- 🔴 高：占故障 50% 以上的原因
- 🟡 中：占 20-40%
- 🟢 低：占 <10%

### 3. 每步必含「预期输出」和「判断」

不能只给命令不给预期结果，用户看到预期输出才知道是否正常：
```python
{
    "action": "检查服务存活",
    "command": "kubectl get pod",
    "expected": "STATUS 列为 Running",      # 必须
    "judgment": "如果不是 Running，说明...",  # 必须
}
```

### 4. 有副作用的操作必含「回退方案」

如果某步操作会改配置/删数据，必须在 rollback 里写回退方法。

### 5. 命令可直接复制执行

命令要完整，参数用 `<占位符>` 标注需替换的部分：
```bash
kubectl get pod -n <namespace> | grep <服务名>
```

---

## 从故障复盘沉淀新 Runbook 的流程

1. **故障发生后**：用 `issue-report-formatter` 整理上报报告
2. **故障解决后**：复盘排查过程，总结关键步骤
3. **按模板写 runbook**：复制本文档的结构模板，填入排查步骤
4. **测试匹配**：用关键词测试能否匹配到新 runbook
5. **团队评审**：让有经验的同事 review 步骤是否合理
6. **更新入库**：追加到 `runbook_lib.py`，重新打包发布

> 💡 这就是运维工具链的价值：发现问题(ssl-cert-monitor) → 上报问题(issue-report-formatter) → 解决问题(runbook-generator) → 沉淀经验(复盘→新 runbook)。
