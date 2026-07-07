# NEXUS 用户管理系统 🔐

> **基于 Flask 的安全用户身份验证管理系统**  
> 设计风格：赛博科技风 · 暗黑霓虹 UI  
> 安全等级：生产级（22 项漏洞已修复）

---

## ✨ 功能特性

- ✅ 用户登录 / 登出
- ✅ Session 会话管理
- ✅ CSRF 跨站请求伪造保护
- ✅ bcrypt 加盐密码哈希
- ✅ 暴力破解防护（IP + 用户名双维度限速）
- ✅ 反用户枚举（虚拟用户混淆）
- ✅ 时序攻击防护（固定延迟 + bcrypt 恒等比较）
- ✅ 安全响应头（CSP / X-Frame / XSS 等）
- ✅ 操作审计日志
- ✅ 重启后限速状态持久化

---

## 🚀 快速启动

### 环境要求

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | ≥ 3.8 | 运行环境 |
| Flask | ≥ 3.0.0 | Web 框架 |
| bcrypt | ≥ 4.0.0 | 密码哈希 |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/jgymh/user-management-system.git
cd user-management-system

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置管理员密码
export ADMIN_PASSWORD="your-admin-password"
export ALICE_PASSWORD="your-alice-password"

# 4. 启动服务
python3 app.py
```

> ⚠️ **安全提示**：如未设置环境变量，系统将自动生成随机密码并在终端输出。

---

## 🌐 访问指南

### 本地访问（本机）

| 路由 | 方法 | 说明 |
|------|------|------|
| `http://127.0.0.1:5000/` | GET | 系统首页（控制台） |
| `http://127.0.0.1:5000/login` | GET / POST | 用户身份验证 |
| `http://127.0.0.1:5000/logout` | GET | 会话终止退出 |

### 局域网访问（同一网络）

```
http://<服务器IP地址>:5000/
```

> 💡 查看本机局域网 IP：
> ```bash
> # Linux / macOS
> ip addr show | grep inet
> # Windows (PowerShell)
> ipconfig | findstr IPv4
> ```

### CURL 接口测试

```bash
# 获取登录页（含 CSRF Token）
curl -c cookies.txt http://127.0.0.1:5000/login

# 提交登录（请先提取 CSRF Token）
curl -X POST http://127.0.0.1:5000/login \
  -b cookies.txt -c cookies.txt \
  -d "username=admin&password=your-password&csrf_token=<TOKEN>"

# 访问首页
curl -b cookies.txt http://127.0.0.1:5000/
```

---

## 🏗️ 项目结构

```
user-mgr/
├── app.py                  # Flask 主应用（含完整安全加固）
├── requirements.txt        # Python 依赖清单
├── .gitignore
├── generate_report.py      # 安全报告生成脚本
├── static/
│   └── css/
│       └── style.css       # 科技风样式表
└── templates/
    ├── base.html           # 基础模板（导航栏 + 背景动效）
    ├── index.html          # 首页控制台
    └── login.html          # 身份验证页
```

---

## 🛡️ 安全漏洞修复清单

### 第一期 — 基础防护（10 项）

| 编号 | 漏洞 | 严重等级 | 修复方案 |
|------|------|---------|---------|
| SEC-001 | 明文密码存储 | 🔴 严重 | bcrypt 加盐哈希 |
| SEC-002 | Secret Key 硬编码 | 🔴 严重 | secrets.token_hex(32) 随机生成 |
| SEC-003 | Debug 模式开启 | 🔴 严重 | debug=False |
| SEC-004 | 无 CSRF 保护 | 🟠 高危 | Token 生成 + 双向校验 + 刷新 |
| SEC-005 | Cookie 无安全属性 | 🟠 高危 | HttpOnly + SameSite + 1h 过期 |
| SEC-006 | 密码展示在前端 | 🟠 高危 | 后端过滤，不传递至模板 |
| SEC-007 | HTML 泄露默认账号 | 🟡 中危 | 清除敏感注释 |
| SEC-008 | 无暴力破解限制 | 🟡 中危 | IP + 用户名双维度 5 次/15分 |
| SEC-009 | 无 HTTPS 传输 | 🟡 中危 | 支持生产环境 HTTPS 模式 |
| SEC-010 | 无输入校验 | 🟢 低危 | 长度 + 空值校验 |

### 第二期 — 深度防护（6 项）

| 编号 | 漏洞 | 严重等级 | 修复方案 |
|------|------|---------|---------|
| SEC-011 | SHA-256 哈希强度不足 | 🔴 严重 | bcrypt rounds=12 慢哈希 |
| SEC-012 | Session Fixation | 🟠 高危 | 登录后 Session 重新生成 |
| SEC-013 | Session 永不过期 | 🟠 高危 | SESSION_PERMANENT + 1h 过期 |
| SEC-014 | 时序攻击 | 🟠 高危 | bcrypt 恒等比较 + 300ms 延迟 |
| SEC-015 | 用户名可枚举 | 🟡 中危 | 虚拟用户混淆认证路径 |
| SEC-016 | 内存明文密码残留 | 🟡 中危 | 变量即时 clear() + del |

### 第三期 — 生产级加固（6 项）

| 编号 | 漏洞 | 严重等级 | 修复方案 |
|------|------|---------|---------|
| SEC-017 | X-Forwarded-For 伪造 | 🔴 严重 | 可信代理白名单 |
| SEC-018 | 源码硬编码密码 | 🔴 严重 | 环境变量读取 |
| SEC-019 | HTTP 明文传输 | 🟠 高危 | 环境区分 + 生产强制 HTTPS |
| SEC-020 | 错误信息泄露 | 🟡 中危 | 统一模糊提示 |
| SEC-021 | 随机延迟偏差 | 🟡 中危 | 固定 300ms 前置延迟 |
| SEC-022 | 计数器重启归零 | 🟡 中危 | JSON 文件持久化 |

---

## 🔒 安全架构（纵深防御模型）

```
┌──────────────────────────────────────┐
│         传输层安全                    │
│  HTTPS / Security Headers / CSP      │
├──────────────────────────────────────┤
│         会话层安全                    │
│  CSRF Token / HttpOnly / SameSite    │
├──────────────────────────────────────┤
│         认证层安全                    │
│  bcrypt / Anti-Timing / Rate Limit   │
├──────────────────────────────────────┤
│         数据层安全                    │
│  环境变量 / 字段过滤 / 审计日志       │
└──────────────────────────────────────┘
```

---

## ⚙️ 生产环境部署

### 环境变量配置

```bash
export FLASK_ENV=production
export ADMIN_PASSWORD="<your-strong-admin-password>"
export ALICE_PASSWORD="<your-strong-alice-password>"
```

### HTTPS 证书配置

```bash
# 使用 Let's Encrypt 免费证书
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem  ./key.pem
```

### 启动服务

```bash
python3 app.py
```

### Nginx 反向代理（推荐）

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 📊 安全评分卡

| 评估维度 | 评分 | 说明 |
|---------|------|------|
| 密码存储安全 | ⭐⭐⭐⭐⭐ | bcrypt + 环境变量 |
| 会话安全 | ⭐⭐⭐⭐☆ | 缺少 Secure flag（开发环境） |
| CSRF 防护 | ⭐⭐⭐⭐⭐ | Token + 刷新机制 |
| 暴力破解防护 | ⭐⭐⭐⭐⭐ | 双维度 + 持久化 |
| 输入验证 | ⭐⭐⭐⭐⭐ | 长度 + 内容校验 |
| 安全配置 | ⭐⭐⭐⭐☆ | HTTPS 需手动启用 |
| 审计日志 | ⭐⭐⭐⭐☆ | 基础日志，可扩展至 SIEM |
| 纵深防御 | ⭐⭐⭐⭐☆ | 四层防护体系 |

---

## 📄 许可协议

MIT License

---

> **报告编号**: NEXUS-SEC-2025-001  
> **最后更新**: 2025-07-07  
> **仓库地址**: [https://github.com/jgymh/user-management-system](https://github.com/jgymh/user-management-system)
