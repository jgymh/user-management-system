import hashlib
import hmac
import secrets
import logging
import json
import os
import time
import sqlite3
import re
import html
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, request, redirect, session, url_for
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
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024
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
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
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


# ===== SQLite 数据库初始化 =====
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "users.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, email TEXT, phone TEXT, balance INTEGER DEFAULT 0)")
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES ('admin', ?, 'admin@example.com', '13800138000', 99999)", (bcrypt.hashpw(b'admin123', bcrypt.gensalt(rounds=12)).decode(),))
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES ('alice', ?, 'alice@example.com', '13900139001', 100)", (bcrypt.hashpw(b'alice2025', bcrypt.gensalt(rounds=12)).decode(),))
    # 为已存在的表添加balance列（如果不存在）
    try:
        c.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")
    except:
        pass
    conn.commit()
    conn.close()
    print("✅ SQLite 数据库初始化完成")

init_db()


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
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
        safe_info = {k: v for k, v in user_info.items() if k not in ("password",)}
    else:
        safe_info = None

    # 搜索功能
    keyword = request.args.get("keyword", "")
    search_results = []
    if keyword:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = "SELECT id, username, email, phone FROM users WHERE username LIKE ? OR email LIKE ?"
        print(f"\n[SQL] 执行查询: {sql} 参数: ['%{keyword}%']")
        try:
            c.execute(sql, ('%' + keyword + '%', '%' + keyword + '%'))
            search_results = c.fetchall()
            print(f"[SQL] 返回 {len(search_results)} 条结果")
        except Exception as e:
            print(f"[SQL] 查询错误: {e}")
        conn.close()

    return render_template("index.html", user=safe_info, keyword=keyword, search_results=search_results)


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


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        ip = get_client_ip()
        now = datetime.now()

        # 速率限制
        cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
        login_attempts[ip]["__register__"] = [
            t for t in login_attempts[ip]["__register__"] if t > cutoff
        ]
        if len(login_attempts[ip]["__register__"]) >= 3:
            return render_template("register.html", error="操作过于频繁，请15分钟后再试！")

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")

        # CSRF 校验
        csrf_token = request.form.get("csrf_token")
        if csrf_token != session.get("csrf_token"):
            return "CSRF token 无效", 400

        # 记录注册尝试
        login_attempts[ip]["__register__"].append(now)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = "INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)"
        print(f"\n[SQL] 执行插入: {sql} 参数: [{username}, {password}, {email}, {phone}]")
        try:
            c.execute(sql, (username, bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode(), email, phone))
            conn.commit()
            print(f"[SQL] 用户 '{username}' 注册成功")
            conn.close()
            return redirect("/login?msg=注册成功，请登录")
        except Exception as e:
            print(f"[SQL] 插入错误: {e}")
            conn.close()
            return render_template("register.html", error=f"注册失败: 用户名可能已存在")

    return render_template("register.html")


@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    search_results = []
    if keyword:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = "SELECT id, username, email, phone FROM users WHERE username LIKE ? OR email LIKE ?"
        print(f"\n[SQL] 执行查询: {sql} 参数: ['%{keyword}%']")
        try:
            c.execute(sql, ('%' + keyword + '%', '%' + keyword + '%'))
            search_results = c.fetchall()
            print(f"[SQL] 返回 {len(search_results)} 条结果")
        except Exception as e:
            print(f"[SQL] 查询错误: {e}")
        conn.close()

    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
        safe_info = {k: v for k, v in user_info.items() if k not in ("password",)}
    else:
        safe_info = None

    return render_template("index.html", user=safe_info, keyword=keyword, search_results=search_results)


# ===== 允许上传的文件类型 =====
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def safe_filename(filename):
    """清理文件名，防止路径穿越"""
    # 去掉路径部分，只保留文件名
    filename = os.path.basename(filename)
    # 去掉非安全字符
    filename = re.sub(r'[^\w\.\-]', '_', filename)
    # 限制文件名长度
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:80] + ext
    return filename


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["GET", "POST"])
def upload():
    # 需要登录才能访问
    if "username" not in session:
        return redirect("/login")

    file_url = None
    error = None

    if request.method == "POST":
        # CSRF 校验
        csrf_token = request.form.get("csrf_token")
        if csrf_token != session.get("csrf_token"):
            return "CSRF token 无效", 400

        if "file" not in request.files:
            error = "没有选择文件"
        else:
            f = request.files["file"]
            if f.filename == "":
                error = "文件名为空"
            else:
                # 修复1: 检查文件扩展名
                if not allowed_file(f.filename):
                    error = "不支持的文件类型，仅允许图片: png/jpg/gif/bmp/webp"
                else:
                    # 修复2: 清理文件名（防路径穿越）
                    filename = safe_filename(f.filename)

                    # 修复3: 如果文件已存在，自动重命名
                    save_path = os.path.join("static/uploads", filename)
                    if os.path.exists(save_path):
                        name, ext = os.path.splitext(filename)
                        filename = f"{name}_{secrets.token_hex(4)}{ext}"
                        save_path = os.path.join("static/uploads", filename)

                    # 修复4: 读取文件内容验证
                    file_data = f.read()
                    if len(file_data) > 16 * 1024 * 1024:
                        error = "文件大小超过 16MB 限制"
                    else:
                        f.seek(0)
                        f.save(save_path)
                        file_url = url_for("static", filename=f"uploads/{filename}")
                        print(f"[UPLOAD] 文件已保存: {save_path} (用户: {session.get('username')})")

    return render_template("upload.html", file_url=file_url, error=error)


@app.route("/profile")
def profile():
    # 需要登录才能访问
    if "username" not in session:
        return redirect("/login")

    username = session.get("username")
    user_data = _get_user_data(username)
    return render_template("profile.html", user=user_data)


@app.route("/recharge", methods=["POST"])
def recharge():
    # 需要登录才能访问
    if "username" not in session:
        return redirect("/login")

    # CSRF 校验
    csrf_token = request.form.get("csrf_token")
    if csrf_token != session.get("csrf_token"):
        return "CSRF token 无效", 400

    username = session.get("username")
    amount = request.form.get("amount", "0")
    try:
        amount_num = int(amount)
        # 校验金额必须为正数
        if amount_num <= 0:
            # 重新查询用户信息再返回页面
            user_data = _get_user_data(username)
            return render_template("profile.html", user=user_data, error="充值金额必须大于0")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # 只充值当前登录用户
        c.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE username=?", (amount_num, username))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[RECHARGE] 错误: {e}")
        user_data = _get_user_data(username)
        return render_template("profile.html", user=user_data, error="充值失败")
    return redirect("/profile")


def _get_user_data(username):
    """辅助函数：根据用户名查询用户资料"""
    if not username:
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, email, phone, balance FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "phone": row[3],
            "balance": row[4]
        }
    return None


@app.route("/page")
def dynamic_page():
    name = request.args.get("name", "")
    page_content = None

    if name:
        # 修复: 使用basename去掉路径部分，防止路径穿越
        name = os.path.basename(name)

        page_path = os.path.join("pages", name)

        if os.path.exists(page_path):
            with open(page_path, "r", encoding="utf-8") as f:
                content = f.read()
                # 基本XSS防护：只允许安全标签
                safe_tags = ['h1','h2','h3','h4','h5','h6','p','br','ul','ol','li','strong','em','a','div','span','table','tr','td','th','thead','tbody','code','pre','hr','blockquote','img','dl','dt','dd']
                for tag in ['script','style','iframe','object','embed','form','input','button','textarea','select','option','link','meta','base']:
                    content = re.sub(rf'<{tag}[^>]*>', '', content, flags=re.IGNORECASE)
                    content = re.sub(rf'</{tag}>', '', content, flags=re.IGNORECASE)
                # 移除onclick等事件处理器
                content = re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
                # 移除javascript:协议链接
                content = re.sub(r'href\s*=\s*["\']\s*javascript\s*:', 'href="#disabled-', content, flags=re.IGNORECASE)
                page_content = content
        else:
            # 尝试加上.html后缀
            page_path_html = os.path.join("pages", name + ".html")
            if os.path.exists(page_path_html):
                with open(page_path_html, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 基本XSS防护：移除危险标签和事件处理器
                    for tag in ['script','style','iframe','object','embed','form','input','button','textarea','select','option','link','meta','base']:
                        content = re.sub(rf'<{tag}[^>]*>', '', content, flags=re.IGNORECASE)
                        content = re.sub(rf'</{tag}>', '', content, flags=re.IGNORECASE)
                    content = re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
                    content = re.sub(r'href\s*=\s*["\']\s*javascript\s*:', 'href="#disabled-', content, flags=re.IGNORECASE)
                    page_content = content
            else:
                page_content = "页面不存在"

    # 获取用户信息用于模板
    username = session.get("username")
    user_info = None; safe_info = None
    if username and username in USERS:
        user_info = USERS[username]
        safe_info = {k: v for k, v in user_info.items() if k not in ("password",)}
    return render_template("index.html", user=safe_info, page_content=page_content)


@app.route("/change-password", methods=["POST"])
def change_password():
    if "username" not in session:
        return redirect("/login")

    # CSRF 校验
    csrf_token = request.form.get("csrf_token")
    if csrf_token != session.get("csrf_token"):
        return "CSRF token 无效", 400

    username = session.get("username")
    new_password = request.form.get("new_password", "")

    if username and new_password:
        USERS[username]["password"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12))
        # 同步更新SQLite数据库（bcrypt哈希存储）
        hashed_pw = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hashed_pw, username))
        conn.commit()
        conn.close()
        print(f"[PASSWORD] 用户 '{username}' 密码已修改")

    return redirect("/profile")


@app.route("/fetch-url", methods=["POST"])
def fetch_url():
    if "username" not in session:
        return redirect("/login")

    url = request.form.get("url", "")
    status_code = None
    response_content = ""
    error = None

    if url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            status_code = resp.getcode()
            content = resp.read().decode("utf-8", errors="replace")
            response_content = content[:5000]
        except urllib.error.HTTPError as e:
            status_code = e.getcode()
            response_content = str(e)
        except urllib.error.URLError as e:
            error = f"URL 请求失败: {e.reason}"
        except Exception as e:
            error = f"请求出错: {str(e)}"

    username = session.get("username")
    user_info = None; safe_info = None
    if username and username in USERS:
        user_info = USERS[username]
        safe_info = {k: v for k, v in user_info.items() if k not in ("password",)}

    return render_template("index.html", user=safe_info, fetch_url=url, fetch_status=status_code, fetch_content=response_content, fetch_error=error)


if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "production":
        print("🔒 以 HTTPS 模式启动...")
        app.run(ssl_context=("cert.pem", "key.pem"), host="0.0.0.0", port=443)
    else:
        print("⚠️  警告：HTTP 模式运行中，密码明文传输！")
        print("💡  生产环境请: export FLASK_ENV=production")
        print("💡  并配置 SSL 证书 cert.pem / key.pem\n")
        app.run(debug=False, host="0.0.0.0", port=5000)
