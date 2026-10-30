# SSL 证书续签操作指引

> 本文档提供各主流平台的证书续签操作指引。当 `ssl-cert-monitor` 报告中出现 🔴 紧急 / 🟡 警告 / 🔴 已过期 域名时，按证书实际颁发平台选择对应流程操作。
>
> **边界声明**：本文档只提供操作指引，不代替实际操作。续签涉及生产证书变更，操作前确认环境、备份旧证书、选择低峰期操作。

---

## 续签前检查清单

无论用哪种平台，续签前都做这几件事：

| # | 检查项 | 方法 |
|---|--------|------|
| 1 | 确认当前证书的颁发者 | `openssl s_client -connect domain:443 -servername domain </dev/null 2>/dev/null | openssl x509 -noout -issuer` |
| 2 | 确认证书覆盖的域名（含 SAN） | 同上，把 `-issuer` 换成 `-text` 或用本 Skill 的 check_certs.py |
| 3 | 确认私钥是否可复用 | 如果怀疑泄露则重新生成；否则可复用 |
| 4 | 备份当前证书和私钥 | `cp fullchain.pem fullchain.pem.bak.$(date +%Y%m%d)` |
| 5 | 确认续签后的部署方式 | Nginx reload / K8s Secret 更新 / CDN 上传，提前确认权限 |

---

## 平台一：Let's Encrypt（免费，推荐自动化）

Let's Encrypt 证书有效期 90 天，**强烈建议用 certbot 自动续签**，不要手动。

### 新申请/续签

```bash
# 安装 certbot（Ubuntu/Debian）
sudo apt update && sudo apt install -y certbot python3-certbot-nginx

# 方式1：自动配置 Nginx（推荐，certbot 自动改配置 + 自动续签）
sudo certbot --nginx -d example.com -d www.example.com

# 方式2：只获取证书，手动配置（webroot 方式）
sudo certbot certonly --webroot -w /var/www/html -d example.com -d www.example.com

# 方式3：DNS 验证（适合泛域名证书）
sudo certbot certonly --manual --preferred-challenges dns -d example.com -d *.example.com
```

### 自动续签

certbot 安装时会自动注册 systemd timer 或 cron，每天检查并自动续签：

```bash
# 查看自动续签状态
sudo systemctl list-timers | grep certbot

# 手动测试续签流程（不会真正续签，只模拟）
sudo certbot renew --dry-run

# 手动强制续签（所有快过期的证书）
sudo certbot renew

# 续签后 reload Nginx
sudo certbot renew --deploy-hook "systemctl reload nginx"
```

### 续签后部署

certbot 生成的文件路径：
```
/etc/letsencrypt/live/example.com/
├── cert.pem        # 网站证书
├── chain.pem       # 中间证书
├── fullchain.pem   # 完整链（网站+中间），Nginx 用这个
└── privkey.pem     # 私钥
```

Nginx 配置：
```nginx
ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
```

---

## 平台二：阿里云数字证书管理服务

### 免费DV证书申请（每个账号每年 20 个免费额度）

1. 登录 [阿里云数字证书管理服务](https://yundun.console.aliyun.com/?p=cas)
2. 左侧「SSL 证书」→「免费证书」→「立即购买」（0 元订单）
3. 创建证书：填写域名 → 选择「DNS 验证」（推荐）或「文件验证」
4. DNS 验证：按提示在阿里云云解析添加 TXT 记录 → 等待验证（通常几分钟）
5. 下载证书：选择「Nginx」格式，得到 `.pem`（证书）和 `.key`（私钥）

### 续签说明

阿里云免费 DV 证书有效期 1 年，**到期后不能续签，只能重新申请**。建议：
- 证书到期前 30 天重新申请新证书
- 申请后替换服务器上的旧证书文件
- CDN 上的证书需同步更新

### 部署到 Nginx

```bash
# 上传证书文件到服务器
# 假设下载的是 example.com.pem 和 example.com.key

# 配置 Nginx
ssl_certificate     /etc/nginx/ssl/example.com.pem;
ssl_certificate_key /etc/nginx/ssl/example.com.key;

# 测试配置 + reload
sudo nginx -t && sudo nginx -s reload
```

### 部署到 K8s Secret（华为云 CCE / 自建 K8s）

```bash
# 创建/更新 TLS Secret
kubectl create secret tls example-com-tls \
  --cert=example.com.pem \
  --key=example.com.key \
  -n your-namespace \
  --dry-run=client -o yaml | kubectl apply -f -

# 确认 Secret 已更新
kubectl get secret example-com-tls -n your-namespace -o yaml
```

### 部署到阿里云 CDN

1. 进入 [CDN 控制台](https://cdn.console.aliyun.com/)
2. 域名管理 → 选择域名 → HTTPS 配置
3. 上传证书（pem + key）或选择已上传的证书
4. 点击「确定」，等待分发（几分钟）

---

## 平台三：腾讯云 SSL 证书

### 免费DV证书申请

1. 登录 [腾讯云 SSL 证书控制台](https://console.cloud.tencent.com/ssl)
2. 「申请免费证书」→ 填写域名 → 选择「DNS 验证」
3. 按提示添加 DNS TXT 记录（如使用腾讯云 DNSPod 则可自动添加）
4. 验证通过后下载证书，选择「Nginx」格式

### 续签说明

腾讯云免费 DV 证书有效期 1 年，同样**到期需重新申请**。

### 部署到 CDN

1. [CDN 控制台](https://console.cloud.tencent.com/cdn) → 域名管理 → HTTPS 配置
2. 选择已上传的证书或上传新证书
3. 配置回源协议（建议 HTTPS 回源）

### 部署到 CLB（负载均衡）

1. [CLB 控制台](https://console.cloud.tencent.com/clb) → 实例管理 → 监听器
2. HTTPS 监听器 → 关联证书 → 选择新证书

---

## 平台四：华为云云证书管理（CCM）

### 免费DV证书申请

1. 登录 [华为云 CCM 控制台](https://console.huaweicloud.com/ccm/)
2. 「证书管理」→「申请证书」→ 选择「DV 免费」
3. 填写域名 → 选择「DNS 验证」（华为云 DNS）或「文件验证」
4. 验证通过后下载证书

### 部署到华为云 CCE（K8s）

```bash
# 方式1：kubectl 创建 Secret
kubectl create secret tls example-com-tls \
  --cert=server.pem \
  --key=server.key \
  -n your-namespace

# 方式2：通过 CCE 控制台
# 工作负载 → 配置管理 → 密钥 → 创建密钥（选择 kubernetes.io/tls 类型）

# 更新 Ingress 引用（如果 ingress 直接引用 secret）
kubectl get ingress -n your-namespace
# Ingress 的 tls 字段引用的 secret 名字不变，Secret 更新后 ingress 自动生效
# 但部分 nginx-ingress-controller 需要手动 reload pod
kubectl rollout restart deployment nginx-ingress-controller -n kube-system
```

### 部署到华为云 CDN

1. [CDN 控制台](https://console.huaweicloud.com/cdn/) → 域名管理
2. 选择域名 → HTTPS 配置 → 证书管理
3. 上传新证书或选择 CCM 中的证书 → 确认

---

## 通用：Nginx 证书替换流程

适用所有平台，证书文件准备好后：

```bash
# 1. 备份旧证书
sudo cp /etc/nginx/ssl/example.com/fullchain.pem /etc/nginx/ssl/example.com/fullchain.pem.bak.$(date +%Y%m%d)
sudo cp /etc/nginx/ssl/example.com/privkey.pem /etc/nginx/ssl/example.com/privkey.pem.bak.$(date +%Y%m%d)

# 2. 替换新证书
sudo cp new_fullchain.pem /etc/nginx/ssl/example.com/fullchain.pem
sudo cp new_privkey.pem /etc/nginx/ssl/example.com/privkey.pem
sudo chmod 600 /etc/nginx/ssl/example.com/privkey.pem

# 3. 测试 Nginx 配置
sudo nginx -t

# 4. reload（不断连接）
sudo nginx -s reload

# 5. 验证
curl -vI https://example.com 2>&1 | grep -E "expire|subject|issuer"
```

### 回滚

如果新证书有问题：

```bash
sudo cp /etc/nginx/ssl/example.com/fullchain.pem.bak.YYYYMMDD /etc/nginx/ssl/example.com/fullchain.pem
sudo cp /etc/nginx/ssl/example.com/privkey.pem.bak.YYYYMMDD /etc/nginx/ssl/example.com/privkey.pem
sudo nginx -t && sudo nginx -s reload
```

---

## 平台选择建议

| 场景 | 推荐平台 | 理由 |
|------|---------|------|
| 个人网站 / 测试环境 | Let's Encrypt + certbot | 免费、自动续签、90 天有效期天然安全 |
| 企业官网（简单） | 阿里云/腾讯云/华为云免费 DV | 免费、1 年有效期、与云厂商集成方便 |
| 企业官网（需 OV） | 付费证书（DigiCert/GlobalSign） | 有企业身份验证 |
| 泛域名证书 | Let's Encrypt（certbot DNS 验证）或付费泛域名证书 | 免费方案需 DNS API 自动化 |
| 金融 / 支付 | 付费 EV 证书 | 最高级别身份验证 |

---

## ⚠️ 安全提醒

- 续签操作涉及私钥，**不要在有外人的屏幕上显示私钥内容**
- 私钥文件传输使用加密通道（SCP over SSH），不要走明文 HTTP
- 续签完成后，**安全删除旧的备份私钥**（确认新证书稳定运行 7 天后）
- 多人协作时，证书续签操作应有审计日志
