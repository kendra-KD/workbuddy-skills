# Growth Log — ops-config-audit

## #001 · 2026-11-05 · 首次创建（v1.0）

### 触发场景
四件套（预防→发现→上报→解决）已形成闭环，但用户希望扩展 skill 类型和范围。运维配置错误是生产事故的重要根因，决定在「预防」前再增加一层「配置审计」。

### 方案选择
- **能力边界**：输入目标环境或配置文件，自动检查 Nginx upstream、SSL 证书、K8s ConfigMap/Secret/Ingress、多环境配置一致性
- **输入方式**：命令行参数，支持单个文件/目录/YAML
- **输出格式**：Markdown 表格 + JSON
- **技术栈**：Python 标准库 + PyYAML，只读审计
- **作用域**：项目级（副业产品，可分发）
- **Fork/从零**：从零设计

### 最终效果
- v1.0 支持 6 种审计类型：
  - nginx-upstream
  - ssl-cert-match
  - k8s-configmap-drift
  - k8s-secret-drift
  - k8s-ingress-cert
  - multi-env-diff

### 关键决策
1. **纯规则引擎不调 AI API**：和四件套保持一致，零成本零延迟。
2. **只读审计不修改配置**：避免误操作风险。
3. **风险等级分级**：高/中/低三级，便于用户优先处理。
