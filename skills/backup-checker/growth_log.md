# Growth Log — backup-checker

> 进化日志。每次制作/迭代由第 ⑦ 步追加一条结构化记录。超过 50 条仅保留最近 30 条。

---

## #001 · 2026-10-31 · 首次创建（v1.0）

### 触发场景
用户（运维工程师）启动第四个 Skill，定位为运维工具链产品矩阵的「预防」环节。前三件套覆盖了发现/上报/解决，第四个需要补全"运维最怕的不是没备份，而是以为备份了真出事才发现是坏的"这个盲区。选定方向：backup-checker 备份健康巡检器。

### 方案选择
- **能力边界**：检查备份元信息（存在/大小/时间戳）+ 5 类内置模板 + 多目标类型（local-file/minio-s3/database/k8s-resource）。只读不写，不执行备份。
- **输入方式**：CSV 巡检清单 + 对话临时输入 + --single 单目标检查
- **健康度分级**：🔴缺失/🟡过期/🟠异常/🟢正常/❌检查失败，按严重度排序
- **技术栈**：Python 标准库 + 调外部 CLI（ssh/mc/aws-cli/kubectl），零第三方 Python 包
- **作用域**：项目级（副业产品，可分发）
- **Fork/从零**：从零设计（Web 检索只找到 wb-migrate 备份 WorkBuddy 软件自身数据，<30% 契合）

### 最终效果
- 7 个文件：SKILL.md + check_backups.py + generate_report.py + backup_templates.md + setup_guide.md + backup_targets_template.csv + growth_log.md + insights.md
- 4 种目标类型检查器：local-file（SSH stat）/ minio-s3（mc/aws-cli）/ database（套 local-file 逻辑）/ k8s-resource（kubectl get）

### 关键决策
1. **MinIO/S3 检查用 mc/aws-cli CLI 而非 Python SDK**（Rule 8）：跟 ssl-cert-monitor 用标准库 ssl 的风格一致，零 Python 第三方依赖。mc 优先，aws-cli 降级。
2. **只读安全红线贯穿全脚本**（Rule 9）：所有 SSH/mc/kubectl 调用只用只读命令（stat/ls/get），绝不写入/删除/执行备份。凭据走环境变量或 mc alias，不硬编码。
3. **健康度五级而非三级**：除缺失/过期/正常外，新增"异常"（存在但太小，疑似空备份）和"检查失败"（工具未装/权限不足），比三态更精确。
4. **模板库通过 CSV 参数化**：5 类模板不写进代码，通过 CSV 的 expected_* 字段参数化，用户改阈值不用改代码。
5. **产品矩阵定位明确**：补全"预防"环节，四件套覆盖预防→发现→上报→解决全生命周期。

### 踩坑记录
| # | 问题 | 根因 | 修复 | 耗时 |
|---|------|------|------|------|
| 1 | init_skill 生成的 SKILL.md 无 slug/displayName/version | 脚手架模板是通用的 TODO 占位 | 手动覆盖写完整 frontmatter | 低 |
| 2 | check_backups.py 的 minio-s3 检查逻辑复杂 | mc JSON 输出格式 + aws-cli 降级 + endpoint 处理 | 拆成主函数 + _check_minio_s3_via_aws 降级函数 | 中 |
| 3 | k8s-resource 检查语义 | K8s 资源不是"备份文件"，而是资源本身的存在性 | 用 kubectl get --ignore-not-found + 检查 creationTimestamp，max_age=0 时不查年龄 | 低 |

### 可复用经验
1. **CLI 降级链设计**：mc 优先 → aws-cli 降级，两者都不可时报"neither installed"而非崩溃。后续涉及多工具支持时复用此模式。
2. **CSV 参数化模板**：把模板的"内容"部分通过 CSV 字段参数化，避免每加一个模板就改代码。
3. **健康度分级要有"检查失败"态**：跟 ssl-cert-monitor 的"失败行"不同，备份检查的失败原因更多样（SSH/mc/kubectl 各自的失败），单独一级便于区分"备份有问题"vs"检查工具有问题"。

### 待观察
- 大批量目标（50+）的性能未测——当前串行 + 15 秒超时，50 目标最坏 750 秒。后续若反馈慢再考虑并发。
- mc JSON 输出格式跨版本兼容性未测——MinIO mc 不同版本 JSON 字段名可能差异（lastModified vs time），脚本已兼容两者。

---

## #002 · 2026-11-05 · v1.1 扩模板（数据驱动升级）

### 触发场景
backup-checker 在 SkillHub 下载数据中增速最快（11-03→11-05 两天从 5 涨到 13，+160%），是四件套里增长最猛的。验证了 v1.0 判断"预防方向需求存在但被低估"——之前下载少是因为发布晚+曝光少，不是需求弱。决定做 v1.1 扩模板顺势放大增速，而非做新 skill。

### 方案选择
- **扩 5 个模板（5→10）**：etcd-snapshot / k8s-configmap-secret / k8s-volumesnapshot / mongodb-dump / clickhouse-backup
- **覆盖方向**：K8s 集群核心（etcd/ConfigMap/PV 快照）+ MongoDB + ClickHouse，补全云原生全栈
- **不改核心代码**：新增 5 模板全部复用已有 local-file / k8s-resource 检查器，只补 references 文档 + CSV 示例 + SKILL.md 模板清单表
- **体验优化 3 项**：SKILL.md 模板清单表扩 10 行 + description 模板数量改 10 + CSV 模板补 5 行示例

### 关键决策
1. **v1.1 不改脚本逻辑**：跟 runbook v1.1 不同，backup-checker 的模板本质是 CSV 配置参数化（Rule: CSV 参数化模板），新增模板不需要改 check_backups.py，风险更低工作量更小。
2. **etcd-snapshot 是最高价值新增**：K8s 集群 etcd 备份是集群恢复底线，丢了等于整个集群状态丢失，但市面通用备份检查工具很少覆盖。这是差异化卖点。
3. **k8s-configmap-secret 利用已有 check_k8s_resource 代码**：v1.0 代码已支持 k8s-resource 类型，只是模板库没列出来。v1.1 补模板文档等于"激活"已有能力。
4. **clickhouse-backup 阈值高于其他数据库**（50MB vs 10MB）：ClickHouse 列存数据量大，沿用 mysql/mongo 的 10MB 阈值会误报，按实际数据特征调整。

### 踩坑记录
| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | CSV 文件首行有 BOM（﻿） | init_skill 脚手架生成时编码 | 追加示例行时保留原行不动，不重新生成文件 |

### 可复用经验
1. **数据驱动迭代的优先级判断**：增速最快的 skill 优先做深度迭代（扩模板/体验优化），比做新 skill 投入产出比高。backup-checker +160% 增速 → 优先于新 skill。
2. **模板扩容不改代码的条件**：当模板本质是 CSV 参数化配置时，扩模板只需改文档+CSV 示例，不碰脚本。判断标准：新增模板是否复用已有 type 检查器。

### 待观察
- v1.1 发布后 download 增速是否进一步加快（验证"扩模板→更多下载"假设）
- 新增的 etcd-snapshot 模板是否成为差异化卖点（市面通用工具少覆盖）
