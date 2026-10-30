# SSL/TLS 证书基础知识参考

> 本文档供 AI 助手查阅，用于回答用户关于 SSL 证书的疑问。非教程文档，按知识点索引式组织。

---

## 1. 证书是什么

SSL/TLS 证书是数字证书的一种，由受信任的证书颁发机构（CA）签发，用于证明网站身份并建立加密连接。

核心作用：
- **身份验证**：证明"你就是你声称的那个域名持有者"
- **加密传输**：建立 TLS 隧道，防止中间人窃听/篡改
- **完整性**：传输内容不可被篡改

一张证书包含的关键信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| Subject（主体） | 证书持有者标识 | `example.com` |
| Issuer（颁发者） | 签发该证书的 CA | `Let's Encrypt R3` |
| notBefore（生效时间） | 证书生效起始 | `2026-01-01T00:00:00Z` |
| notAfter（到期时间） | 证书失效时间 | `2026-04-01T00:00:00Z` |
| SAN（subjectAltName） | 证书覆盖的域名列表 | `example.com, www.example.com` |
| 签名算法 | CA 用来签名的算法 | `SHA256withRSA` / `ECDSA` |
| 公钥 | 用于密钥交换的公钥 | RSA 2048 / ECC P-256 |

---

## 2. 证书类型

### 按验证级别

| 类型 | 验证方式 | 下发速度 | 适用场景 | 浏览器标识 |
|------|---------|---------|---------|-----------|
| DV（Domain Validation） | 只验证域名所有权 | 分钟级 | 个人网站、测试环境 | 普通锁标 |
| OV（Organization Validation） | 验证域名+企业资质 | 1-3 天 | 企业官网、SaaS | 普通锁标 |
| EV（Extended Validation） | 严格企业+电话核实 | 3-7 天 | 金融、支付、政务 | 曾显示绿色地址栏（Chrome 已移除） |

### 按覆盖范围

| 类型 | 说明 | 示例 |
|------|------|------|
| 单域名证书 | 只保护一个域名 | `example.com` |
| 泛域名（Wildcard） | 保护一个域名及其所有一级子域 | `*.example.com` 覆盖 `www.example.com`、`api.example.com` 等 |
| 多域名（SAN/UCC） | 一张证书保护多个域名 | `example.com, blog.example.com, api.other.com` |

### 按费用

| 类型 | 说明 |
|------|------|
| 免费证书 | Let's Encrypt、ZeroSSL、阿里云/腾讯云/华为云免费 DV 证书 |
| 付费证书 | OV/EV 证书、泛域名证书、特定品牌（DigiCert、GlobalSign 等） |

---

## 3. 证书链

浏览器信任一个证书，实际是信任一条链：

```
根证书（Root CA）
  └── 中间证书（Intermediate CA）
        └── 网站证书（Leaf / End-Entity Certificate）
```

- **根证书**：预置在操作系统/浏览器的信任库中，自签名。
- **中间证书**：由根 CA 签发，用于签发终端证书，隔离风险。
- **网站证书**：由中间 CA 签发，部署在服务器上。

### 链不完整的后果

如果服务器只返回网站证书、没返回中间证书：
- 部分浏览器（有缓存中间证书的）能正常验证
- 部分浏览器/客户端（curl、Python ssl 模块等）会报 `unable to get local issuer certificate`
- 本 Skill 的 `check_certs.py` 会标记 `chain_incomplete: true` 并告警

### 修复方法

在 Nginx 配置中把中间证书拼接到网站证书后面：

```nginx
ssl_certificate     /path/to/fullchain.pem;  # 网站证书 + 中间证书拼接
# 不要只用 cert.pem（只含网站证书）
```

Let's Encrypt 的 certbot 自动生成 `fullchain.pem`，已包含完整链。

---

## 4. SAN（Subject Alternative Name）

SAN 是现代证书标记"这张证书覆盖哪些域名"的字段，取代了旧的 Common Name（CN）。

- 现代浏览器**只看 SAN，不看 CN**——CN 里写了 `example.com` 但 SAN 里没有，仍会报域名不匹配。
- 多域名证书就是靠 SAN 字段实现"一证多域"。
- 泛域名在 SAN 中表现为 `*.example.com`。

本 Skill 的检查脚本会提取完整 SAN 列表，报告里展示（超 3 个时截断）。

---

## 5. 证书格式

| 格式 | 扩展名 | 特点 | 常见用途 |
|------|--------|------|---------|
| PEM | `.pem` `.crt` `.key` | Base64 编码，文本格式，最通用 | Nginx、Apache、K8s Secret |
| DER | `.der` | 二进制格式 | Java、部分 CA 后台 |
| PKCS#12 (PFX) | `.pfx` `.p12` | 二进制，含证书+私钥，有密码 | IIS、Windows |
| PKCS#7 | `.p7b` `.p7c` | 二进制，只含证书链不含私钥 | 部分 CA 后台导出 |

### 转换命令（OpenSSL）

```bash
# PEM → DER
openssl x509 -in cert.pem -outform der -out cert.der

# DER → PEM
openssl x509 -in cert.der -inform der -outform pem -out cert.pem

# PEM → PFX（需要私钥）
openssl pkcs12 -export -in cert.pem -inkey key.pem -out cert.pfx

# PFX → PEM（拆出证书和私钥）
openssl pkcs12 -in cert.pfx -nodes -out cert_and_key.pem
```

---

## 6. 私钥

证书配套的私钥是证书安全的核心——私钥泄露等于证书作废。

- **RSA**：传统算法，兼容性最好，2048 位是当前最低标准，4096 位更安全但握手更慢。
- **ECC（ECDSA）**：更现代，同等安全强度下密钥更短、握手更快，推荐 P-256 曲线。

### 私钥生成

```bash
# RSA 2048
openssl genrsa -out key.pem 2048

# ECC P-256
openssl ecparam -genkey -name prime256v1 -noout -out key.pem
```

### ⚠️ 安全红线

- 私钥绝不入库 git，不入日志，不上传任何外部服务
- 私钥文件权限设为 `600`（仅所有者可读写）
- 续签时如果怀疑私钥泄露，选择"重新生成密钥对"而非"复用旧私钥"

---

## 7. 证书常见问题速查

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| 浏览器显示"不安全" | 证书过期 / 自签名 / 域名不匹配 | 查 notAfter、SAN、CA 是否被信任 |
| curl 报 `unable to get local issuer certificate` | 中间证书未部署 / 系统 CA 库过旧 | 检查 fullchain.pem、更新 ca-certificates |
| curl 报 `SSL_ERROR_NO_CYPHER_OVERLAP` | 服务器/客户端加密套件不匹配 | 检查 Nginx `ssl_ciphers` 配置、TLS 版本 |
| 浏览器报 `ERR_CERT_COMMON_NAME_INVALID` | CN 写了域名但 SAN 没写 | 现代浏览器只认 SAN，续签时把域名加进 SAN |
| Python ssl 模块验证失败但浏览器正常 | Windows 下 Python CA 库不完整 | 本 Skill 用不验证模式绕过；生产环境应加载系统证书 |
| 证书提前过期 | 证书有效期本来就短（Let's Encrypt 90 天） | 不是 bug，设计如此，需自动续签 |
| 泛域名证书对 `a.b.example.com` 无效 | 泛域名只覆盖一级子域 | 需额外申请 `*.b.example.com` 或用多域名证书 |

---

## 8. 有效期趋势

| 时间段 | 最长有效期 | 背景 |
|--------|-----------|------|
| 2015 年前 | 5 年 | 早期标准 |
| 2015-2018 | 3 年 | CA/B 论坛缩短 |
| 2018-2025 | 825 天（约 2 年 3 个月） | 苹果推动缩短 |
| 2025 起 | 47 天 | 新标准逐步落地，Let's Encrypt 已支持短有效期 |

**趋势解读**：有效期越来越短 → 手动续签不可持续 → **自动化续签是必然方向**。

---

## 9. 与本 Skill 的关系

| 用户疑问 | 查阅章节 |
|---------|---------|
| "证书为什么会过期？" | 第 8 节 有效期趋势 |
| "SAN 是什么？为什么我的证书不匹配？" | 第 4 节 SAN |
| "我的证书链不完整是什么意思？" | 第 3 节 证书链 + check_certs.py 的 chain_incomplete 字段 |
| "该用 RSA 还是 ECC？" | 第 6 节 私钥 |
| "免费证书和付费证书有什么区别？" | 第 2 节 证书类型 - 按费用 |
| "怎么把 PEM 转成 PFX？" | 第 5 节 格式转换 |
