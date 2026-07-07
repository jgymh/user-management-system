import hashlib
import hmac
import secrets
import logging
import json
import os
import time
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, request, redirect, session
import bcrypt

# ===== 日志配置 =====
logging.basicConfig(
    filename="audit.log",
    level=logging.INFO,
    format="%(asctime)s [AUDIT] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = Flask(__name__)

# ===== Secret Key =====
app.secret_key = secrets.token_hex(32)

# ===== Session/Cookie 安全配置 =====
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)
)

# ===== 可信代理列表（仅这些 IP 发来的 X-Forwarded-For 才可信）=====
TRUSTED_PROXIES = {"127.0.0.1", "::1"}


def get_client_ip():
    """获取真实客户端 IP（仅信任已知代理的 X-Forwarded-For 头）"""
    xff = request.headers.get("X-Forwarded-For")
    if xff and request.remote_addr in TRUSTED_PROXIES:
        return xff.split(",")[0].strip()
    return request.remote_addr


# ===== 安全响应头 =====
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ===== 用户数据库 - 密码从环境变量读取 =====
USERS = {}

def _init_users():
    """从环境变量初始化用户，避免源码硬编码密码"""
    users_config = {}

    # admin：优先用环境变量 ADMIN_PASSWORD，否则随机生成并打印警告
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_pw:
        admin_pw = secrets.token_urlsafe(12)
        logging.warning(
            f"⚠️ 未设置 ADMIN_PASSWORD 环境变量，已随机生成: {admin_pw}"
        )
        print(f"\n{'='*50}")
        print(f"⚠️  警告：未设置 ADMIN_PASSWORD 环境变量")
        print(f"🔑  本次随机生成的 admin 密码: {admin_pw}")
        print(f"💡  设置方式: export ADMIN_PASSWORD='你的密码'")
        print(f"{'='*50}\n")

    users_config["admin"] = {
        "username": "admin",
        "role": "admin",
        "email": "admin@example.com",
        "phone": "13800138000",
        "balance": 99999
    }
    users_config["admin"]["password"] = bcrypt.hashpw(
        admin_pw.encode(), bcrypt.gensalt(rounds=12)
    )

    # alice：同理
    alice_pw = os.environ.get("ALICE_PASSWORD", "")
    if not alice_pw:
        alice_pw = secrets.token_urlsafe(12)
        logging.warning(f"⚠️ 未设置 ALICE_PASSWORD 环境变量，已随机生成: {alice_pw}")

    users_config["alice"] = {
        "username": "alice",
        "role": "user",
        "email": "alice@example.com",
        "phone": "13900139001",
        "balance": 100
    }
    users_config["alice"]["password"] = bcrypt.hashpw(
        alice_pw.encode(), bcrypt.gensalt(rounds=12)
    )

    return users_config

USERS = _init_users()


# ===== CSRF Token =====
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)


# ===== 暴力破解防护 =====
LOGIN_ATTEMPTS_FILE = "/tmp/flask_login_attempts.json"
login_attempts: dict = defaultdict(lambda: defaultdict(list))
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _save_attempts():
    """持久化登录尝试记录到文件，防止重启丢失"""
    data = {}
    for ip, users in login_attempts.items():
        data[ip] = {}
        for user, times in users.items():
            data[ip][user] = [t.isoformat() for t in times]
    try:
        with open(LOGIN_ATTEMPTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _load_attempts():
    """启动时从文件恢复登录尝试记录"""
    try:
        with open(LOGIN_ATTEMPTS_FILE) as f:
            data = json.load(f)
        for ip, users in data.items():
            for user, times in users.items():
                login_attempts[ip][user] = [
                    datetime.fromisoformat(t) for t in times
                ]
    except (FileNotFoundError, json.JSONDecodeError):
        pass


_load_attempts()


@app.route("/")
def index():
    username = session.get("username")
    if username and username in USERS:
        user_info = USERS[username]
        safe_info = {k: v for k, v in user_info.items() if k not in ("password",)}
    else:
        safe_info = None
    return render_template("index.html", user=safe_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = get_client_ip()
        now = datetime.now()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # 输入校验
        if len(username) > 50 or len(password) > 128:
            return render_template("login.html", error="输入内容过长！")
        if not username or not password:
            return render_template("login.html", error="用户名和密码不能为空！")

        # CSRF 校验
        csrf_token = request.form.get("csrf_token")
        if csrf_token != session.get("csrf_token"):
            return "CSRF token 无效", 400

        # ==== 固定延迟防时序攻击（在密码比对前执行）====
        time.sleep(0.3)

        # ==== 暴力破解防护 ====
        cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
        login_attempts[ip][username] = [
            t for t in login_attempts[ip][username] if t > cutoff
        ]

        ip_attempts = sum(len(times) for times in login_attempts[ip].values())
        user_attempts = len(login_attempts[ip][username])

        if ip_attempts >= MAX_ATTEMPTS or user_attempts >= MAX_ATTEMPTS:
            logging.warning(
                f"登录被锁定 - 用户: {username}, IP: {ip}, "
                f"IP尝试次数: {ip_attempts}, 用户尝试次数: {user_attempts}"
            )
            return render_template("login.html", error="账号或IP已被锁定，请15分钟后再试！")

        # ===== 反用户枚举 =====
        user = USERS.get(username)
        is_fake_user = False
        if user is None:
            fake_hash = bcrypt.hashpw(b"dummy_fake_dummy", bcrypt.gensalt(rounds=12))
            user = {"password": fake_hash}
            is_fake_user = True

        # ===== bcrypt 恒等时间密码比对 =====
        password_ok = bcrypt.checkpw(password.encode(), user["password"])

        if password_ok and not is_fake_user:
            login_attempts[ip][username].clear()
            _save_attempts()

            session["username"] = username
            session["csrf_token"] = secrets.token_hex(16)
            session.permanent = True

            logging.info(f"登录成功 - 用户: {username}, IP: {ip}")
            return redirect("/")
        else:
            login_attempts[ip][username].append(now)
            _save_attempts()

            logging.warning(f"登录失败 - 用户: {username}, IP: {ip}")

            # 不透露剩余次数，只给模糊提示
            return render_template("login.html", error="用户名或密码错误！")

    return render_template("login.html")


@app.route("/logout")
def logout():
    username = session.get("username", "unknown")
    ip = get_client_ip()
    logging.info(f"登出 - 用户: {username}, IP: {ip}")
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "production":
        print("🔒 以 HTTPS 模式启动...")
        app.run(ssl_context=("cert.pem", "key.pem"), host="0.0.0.0", port=443)
    else:
        print("⚠️  警告：HTTP 模式运行中，密码明文传输！")
        print("💡  生产环境请: export FLASK_ENV=production")
        print("💡  并配置 SSL 证书 cert.pem / key.pem\n")
        app.run(debug=False, host="0.0.0.0", port=5000)
