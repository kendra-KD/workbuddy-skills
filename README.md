# WorkBuddy Skills

> Kendra 的 WorkBuddy Skill 开源合集 —— 把运维经验沉淀成可复用的自动化技能

## 这是什么？

这里是我在 [WorkBuddy](https://www.workbuddy.cn) 平台上开发和发布的 Skill 源码合集。每个 Skill 是一个独立的自动化技能包，解决一个具体的运维 / 技术 / 办公场景问题。

Skill 可以通过 WorkBuddy 客户端加载，让 AI 助手在对话中自动触发执行。

## 运维工具链 · 产品矩阵

三个 Skill 覆盖运维故障的完整生命周期：

```
发现问题 → 上报问题 → 解决问题 → 沉淀经验
   │          │          │          │
   ▼          ▼          ▼          ▼
ssl-cert-   issue-     runbook-    复盘→新
monitor     report-    generator   runbook
            formatter
```

- **ssl-cert-monitor**：批量检查证书到期，发现问题
- **issue-report-formatter**：把故障描述整理成标准上报报告，含 AI 协作模式
- **runbook-generator**：输入故障特征匹配预置排查步骤，引导解决问题

## Skills 清单

| Skill | 分类 | 说明 | 状态 |
|-------|------|------|------|
| [ssl-cert-monitor](./skills/ssl-cert-monitor/) | 运维技术 | SSL/TLS 证书到期批量巡检，按紧急度排序生成 Markdown 报告 + JSON 数据，附 4 平台续签指引 | ✅ v1.1 已发布 |
| [issue-report-formatter](./skills/issue-report-formatter/) | 运维技术 | 运维问题上报格式化器，把零散报错描述+环境信息整理成标准化上报报告，自动分级紧急度，v1.1 新增 AI 协作三件套（提示词+排查清单+诊断假设树） | ✅ v1.1 已发布 |
| [runbook-generator](./skills/runbook-generator/) | 运维技术 | 运维故障 Runbook 生成器，输入故障特征匹配 10 个预置实战 runbook（502/503/504/timeout/cert-expiry/pod-crash/minio-500/disk-full/oom），输出排查步骤+验证+回退+根因假设树。SkillHub slug: ops-fault-runbook | ✅ v1.0 已发布 |

### 分类规划

- **运维技术类**：SSL 巡检、K8s 排障、服务器健康检查、日志分析 ……
- **其他技术类**：API 调试、代码审查、CI/CD 辅助 ……
- **日常办公类**：文档处理、表格清洗、会议纪要 ……
- **生活类**：记账、习惯追踪 ……

## 如何使用？

### 方式一：下载 zip 导入 WorkBuddy

1. 进入对应 Skill 目录，下载该 Skill 的 zip 包（见 Release）
2. 打开 WorkBuddy 客户端 → 左侧「专家·技能·连接器」
3. 点「添加技能」→「上传技能」→ 拖入 zip 文件
4. 安装完成后，在对话里用触发短语调用即可

### 方式二：直接克隆源码

```bash
git clone https://github.com/kendra-KD/workbuddy-skills.git
```

把对应 Skill 目录复制到 `~/.workbuddy/skills/` 即可本地使用。

## 每个 Skill 包含什么？

```
skill-name/
├── SKILL.md          ← 主入口（元数据 + 工作流程）
├── scripts/          ← 可执行脚本（纯标准库，零依赖）
├── references/       ← 参考文档（知识库 + 操作指南）
├── assets/           ← 模板文件（CSV / 配置示例）
└── growth_log.md     ← 开发记录（踩坑 + 经验沉淀）
```

## 技术原则

- **纯标准库优先**：脚本尽量只用 Python 标准库，降低部署门槛
- **面向普遍场景**：不绑定特定公司 / 域名 / 云厂商
- **双输出**：人类可读报告 + 机器可读数据
- **容错优先**：单点失败不中断整体流程

## 关于我

云运维工程师，负责多家公司的服务器 / K8s / 证书管理。在这里把日常运维经验沉淀成 Skill，既自用也分享给社区。

## License

MIT License - 详见 [LICENSE](./LICENSE)
