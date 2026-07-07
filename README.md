# NEXUS 用户管理系统 🔐

> 基于 Flask 的安全用户身份验证管理系统 \
> 设计风格：赛博科技风 · 暗黑霓虹 UI

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

## 🖥️ 页面预览

| 页面 | 描述 |
|------|------|
| `/login` | NEXUS 科技风登录页 |
| `/` | 用户控制台首页 |
| `/logout` | 安全登出 |

## 🚀 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置环境变量

```bash
export ADMIN_PASSWORD="你的admin密码"
export ALICE_PASSWORD="你的alice密码"
```

> 如果不设置，启动时会随机生成密码并打印在终端上

### 3. 启动服务

```bash
python3 app.py
```

### 4. 访问

```
http://127.0.0.1:5000
```

## 🔒 安全架构

```
┌─────────────────────────────────────┐
│           HTTPS (推荐)               │
├─────────────────────────────────────┤
│  Security Headers (CSP/X-Frame/...) │
├─────────────────────────────────────┤
│  CSRF Token Protection              │
├─────────────────────────────────────┤
│  Session Mgmt (HttpOnly/SameSite)   │
├─────────────────────────────────────┤
│  Rate Limiting (IP + Username)      │
├─────────────────────────────────────┤
│  bcrypt Password Hashing            │
├─────────────────────────────────────┤
│  Anti-Enumeration (Fake User)       │
├─────────────────────────────────────┤
│  Timing Attack Protection           │
└─────────────────────────────────────┘
```

## 📁 项目结构

```
user-mgr/
├── app.py                  # Flask 主应用（含完整安全加固）
├── requirements.txt        # Python 依赖
├── .gitignore
├── static/
│   └── css/
│       └── style.css       # 科技风样式
└── templates/
    ├── base.html           # 基础模板（导航栏）
    ├── index.html          # 首页/控制台
    └── login.html          # 登录页
```

## 🛡️ 已修复安全漏洞

### 第一期 — 基础防护（10项）
- 明文密码 → bcrypt 加盐哈希
- Secret Key 硬编码 → 随机生成
- Debug 模式 → 关闭
- CSRF 保护
- Cookie 安全属性
- 密码前端展示 → 过滤
- HTML 泄露账号 → 清除
- 暴力破解保护
- 输入校验
- Session 过期机制

### 第二期 — 深度防护（6项）
- SHA-256 → bcrypt 慢哈希
- Session Fixation 防护
- Session 永久标志启用
- 时序攻击防护
- 反用户枚举
- 安全响应头

### 第三期 — 生产级加固（6项）
- X-Forwarded-For 伪造防护
- 源码明文密码 → 环境变量
- HTTPS 模式支持
- 模糊化错误信息
- 计数器持久化

## ⚙️ 生产环境部署

```bash
export FLASK_ENV=production
export ADMIN_PASSWORD="your-strong-password"
export ALICE_PASSWORD="your-other-password"
# 配置 SSL 证书 cert.pem + key.pem
python3 app.py
```

## 📄 开源协议

MIT License
