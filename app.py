from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import smtplib
from email.mime.text import MIMEText
import sqlite3, os, subprocess, time, hashlib, jwt, requests as req

app = Flask(__name__)
app.secret_key = "supersecret123"                      # VULN: hardcoded secret key
app.config["SESSION_COOKIE_HTTPONLY"] = False          # VULN: cookie readable by JS
app.config["SESSION_COOKIE_SAMESITE"] = None           # VULN: allows CSRF
app.config["SESSION_COOKIE_SECURE"] = False             # VULN: works over plain HTTP
JWT_SECRET = "secret"                                  # VULN: weak JWT secret
MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
MAIL_PORT   = int(os.environ.get("MAIL_PORT", 1025))

def send_reset_email(to_email, username, token):
    reset_url = f"http://172.17.0.1:5000/reset-password?step=reset&token={token}&username={username}"
    body = f"""Hi {username},

You received this email because you requested a password reset on FaultShop.

Click the link below to continue:

{reset_url}

If you did not request this, you can safely ignore this message.

- The FaultShop Team
"""
    msg = MIMEText(body)
    msg["Subject"] = "Password reset - FaultShop"
    msg["From"]    = "noreply@faultshop.com"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
            smtp.sendmail("noreply@faultshop.com", to_email, msg.as_string())
    except Exception as e:
        print(f"Error sending email: {e}")

UPLOAD_FOLDER   = "static/uploads"
INVOICES_FOLDER = "invoices"
DB = "db/shop.db"

# ─── helpers ───────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def after_request(response):
    # VULN A02:2025 - no security headers set
    # In production these should be present:
    # X-Frame-Options, X-Content-Type-Options, Content-Security-Policy, etc.
    return response

app.after_request(after_request)

# ─── PUBLIC ROUTES ─────────────────────────────────────────

@app.route("/")
def index():
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    return render_template("index.html", products=products, user=session.get("user"))

@app.route("/search")
def search():
    q = request.args.get("q", "")
    db = get_db()
    products = db.execute("SELECT * FROM products WHERE name LIKE ?", (f"%{q}%",)).fetchall()
    # VULN A05:2025 - Reflected XSS via |safe filter in template
    return render_template("search.html", products=products, query=q, user=session.get("user"))

@app.route("/product/<int:pid>", methods=["GET", "POST"])
def product(pid):
    db = get_db()
    prod = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if request.method == "POST" and session.get("user"):
        review = request.form.get("review", "")
        # VULN A05:2025 - Stored XSS: user input saved without sanitization
        db.execute("INSERT INTO reviews (product_id,user_id,content) VALUES (?,?,?)",
                   (pid, session["user"]["id"], review))
        db.commit()
    reviews = db.execute(
        "SELECT r.*,u.username FROM reviews r JOIN users u ON r.user_id=u.id WHERE r.product_id=?",
        (pid,)).fetchall()
    return render_template("product.html", product=prod, reviews=reviews, user=session.get("user"))

# ─── AUTH ──────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        db = get_db()
        # VULN A05:2025 - SQL Injection: raw string interpolation in query
        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
        user = db.execute(query).fetchone()
        if user:
            session["user"] = dict(user)
            return redirect(url_for("dashboard"))
        error = "Invalid credentials"
    return render_template("login.html", error=error, user=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email    = request.form.get("email", "")
        db = get_db()
        try:
            # VULN A04:2025 - password stored in plaintext
            db.execute("INSERT INTO users (username,password,email,role) VALUES (?,?,?,?)",
                       (username, password, email, "user"))
            db.commit()
            return redirect(url_for("login"))
        except:
            error = "Username already taken"
    return render_template("register.html", error=error, user=None)

# ─── PASSWORD RESET ────────────────────────────────────────

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        username = request.form.get("username", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user:
            # VULN A07:2025 - predictable token: MD5(username + Unix timestamp)
            token = hashlib.md5(f"{username}{int(time.time())}".encode()).hexdigest()
            db.execute("DELETE FROM password_resets WHERE username=?", (username,))
            db.execute("INSERT INTO password_resets (username, token, created_at) VALUES (?,?,?)",
                       (username, token, int(time.time())))
            db.commit()
            send_reset_email(user["email"], username, token)
            return render_template("reset_password.html", step="sent",
                                   username=username, user=None)
        error = "User not found"
        return render_template("reset_password.html", step="request", error=error, user=None)
    step     = request.args.get("step", "request")
    token    = request.args.get("token", "")
    username = request.args.get("username", "")
    return render_template("reset_password.html", step=step, token=token, username=username, user=None)

@app.route("/reset-password/confirm", methods=["POST"])
def reset_confirm():
    username = request.form.get("username", "")
    token    = request.form.get("token", "")
    password = request.form.get("password", "")
    db = get_db()
    valid = db.execute(
        "SELECT * FROM password_resets WHERE username=? AND token=?",
        (username, token)
    ).fetchone()
    if not valid:
        return "Invalid or expired token", 400
    db.execute("UPDATE users SET password=? WHERE username=?", (password, username))
    db.execute("DELETE FROM password_resets WHERE username=?", (username,))
    db.commit()
    return redirect(url_for("login"))

# ─── DASHBOARD ─────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = get_db()
    # Only shows orders belonging to the current user — IDOR is in /order/<id>
    orders = db.execute(
        "SELECT o.*,u.username FROM orders o JOIN users u ON o.user_id=u.id WHERE o.user_id=?",
        (session["user"]["id"],)
    ).fetchall()
    return render_template("dashboard.html", orders=orders, user=session.get("user"))

@app.route("/order/<int:order_id>")
def order_detail(order_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    db = get_db()
    # VULN A01:2025 - IDOR: no check that the order belongs to the current user
    order = db.execute(
        "SELECT o.*,u.username,u.email FROM orders o JOIN users u ON o.user_id=u.id WHERE o.id=?",
        (order_id,)).fetchone()
    if not order:
        return "Order not found", 404
    return render_template("order_detail.html", order=order, user=session.get("user"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if not session.get("user"):
        return redirect(url_for("login"))
    if request.method == "POST":
        card   = request.form.get("card", "")
        expiry = request.form.get("expiry", "")
        cvv    = request.form.get("cvv", "")
        total  = request.form.get("total", "99.99")
        db = get_db()
        # VULN A04:2025 - card data stored in plaintext (PCI-DSS violation)
        db.execute(
            "INSERT INTO orders (user_id,card_number,expiry,cvv,total,status) VALUES (?,?,?,?,?,'Paid')",
            (session["user"]["id"], card, expiry, cvv, total))
        db.commit()
        return redirect(url_for("dashboard"))
    return render_template("checkout.html", user=session.get("user"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("user"):
        return redirect(url_for("login"))
    msg = None
    if request.method == "POST":
        f = request.files.get("file")
        if f:
            # VULN A02:2025 - no file type validation
            path = os.path.join(UPLOAD_FOLDER, f.filename)
            f.save(path)
            msg = f"File uploaded: /static/uploads/{f.filename}"
    return render_template("upload.html", msg=msg, user=session.get("user"))

# ─── INVOICES - PATH TRAVERSAL ─────────────────────────────

@app.route("/invoices")
def invoices():
    if not session.get("user"):
        return redirect(url_for("login"))
    files = os.listdir(INVOICES_FOLDER)
    # Only exposes invoice files, not internal files
    invoices_list = [f for f in files if f.startswith("invoice_") and f.endswith(".txt")]
    return render_template("invoices.html", invoices=invoices_list, user=session.get("user"))

@app.route("/download")
def download():
    if not session.get("user"):
        return redirect(url_for("login"))
    filename = request.args.get("file", "")
    # VULN A01:2025 - Path Traversal: filename not sanitized
    filepath = os.path.join(INVOICES_FOLDER, filename)
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        return Response(content, mimetype="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        return f"Error reading file: {str(e)}", 404

# ─── BALANCE TRANSFER - CSRF ───────────────────────────────

@app.route("/transfer-balance", methods=["POST"])
def transfer_balance():
    if not session.get("user"):
        return redirect(url_for("login"))
    recipient = request.form.get("recipient", "")
    amount    = float(request.form.get("amount", 0))
    sender    = session["user"]["username"]
    db = get_db()
    # VULN A02:2025 - CSRF: no anti-CSRF token
    # Any external page can trigger this transfer silently
    current_balance = db.execute(
        "SELECT balance FROM users WHERE username=?", (sender,)
    ).fetchone()
    if not current_balance or current_balance["balance"] < amount:
        return redirect(url_for("my_account"))
    db.execute("UPDATE users SET balance = balance - ? WHERE username=?", (amount, sender))
    db.execute("UPDATE users SET balance = balance + ? WHERE username=?", (amount, recipient))
    db.commit()
    return redirect(url_for("my_account"))

# ─── MY ACCOUNT ────────────────────────────────────────────

@app.route("/my-account", methods=["GET", "POST"])
def my_account():
    if not session.get("user"):
        return redirect(url_for("login"))
    msg = None
    if request.method == "POST":
        new_email = request.form.get("email", "")
        # VULN A02:2025 - CSRF: no anti-CSRF token
        db = get_db()
        db.execute("UPDATE users SET email=? WHERE id=?",
                   (new_email, session["user"]["id"]))
        db.commit()
        session["user"]["email"] = new_email
        msg = "Email updated successfully"
    db = get_db()
    user_data = db.execute("SELECT * FROM users WHERE id=?",
                           (session["user"]["id"],)).fetchone()
    return render_template("my_account.html", user=user_data, msg=msg)

# ─── ADMIN ─────────────────────────────────────────────────

@app.route("/admin")
def admin():
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return render_template("admin_denied.html", user=user), 403
    db = get_db()
    users  = db.execute("SELECT * FROM users").fetchall()
    orders = db.execute(
        "SELECT o.*,u.username FROM orders o JOIN users u ON o.user_id=u.id"
    ).fetchall()
    return render_template("admin.html", users=users, orders=orders, user=user)

@app.route("/admin/tools", methods=["GET", "POST"])
def admin_tools():
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return render_template("admin_denied.html", user=user), 403
    output = None
    if request.method == "POST":
        host = request.form.get("host", "")
        # VULN A05:2025 - Command Injection: unsanitized input passed directly to shell
        try:
            result = subprocess.run(
                f"ping -c 2 {host}",
                shell=True, capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            output = "Timeout: host is not responding"
    return render_template("admin_tools.html", output=output, user=user)

# ─── REST API ──────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    # VULN A07:2025 - no rate limiting (brute-force via API)
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username=? AND password=?", (username, password)
    ).fetchone()
    if user:
        # VULN A07:2025 - JWT signed with a weak secret
        token = jwt.encode(
            {"user_id": user["id"], "username": user["username"], "role": user["role"]},
            JWT_SECRET, algorithm="HS256")
        return jsonify({"token": token, "role": user["role"]})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/profile")
def api_profile():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        # VULN A07:2025 - JWT signature not verified (verify_signature=False)
        data = jwt.decode(token, options={"verify_signature": False})
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": "Invalid token", "detail": str(e)}), 401

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    email    = data.get("email", "")
    # VULN A08:2025 - Mass Assignment: client can supply 'role' field directly
    role = data.get("role", "user")
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username,password,email,role) VALUES (?,?,?,?)",
            (username, password, email, role))
        db.commit()
        return jsonify({"message": "User created", "username": username, "role": role}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/users")
def api_users():
    # VULN A01:2025 - unauthenticated endpoint, no token required
    # VULN API3 - Excessive Data Exposure: returns passwords in plaintext
    db = get_db()
    users = db.execute("SELECT id,username,email,password,role FROM users").fetchall()
    return jsonify([dict(u) for u in users])

@app.route("/api/admin/users")
def api_admin_users():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    # VULN API5 - Broken Function Level Authorization: only checks token presence, not role
    if not token:
        return jsonify({"error": "Token required"}), 401
    db = get_db()
    users  = db.execute("SELECT * FROM users").fetchall()
    orders = db.execute("SELECT * FROM orders").fetchall()
    return jsonify({"users": [dict(u) for u in users], "orders": [dict(o) for o in orders]})

@app.route("/api/products/import", methods=["POST"])
def import_product():
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    url = data.get("url", "")
    try:
        # VULN A01:2025 (SSRF) - fetches any URL with no restriction
        response = req.get(url, timeout=5)
        return jsonify({
            "status": "ok",
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "content_preview": response.text[:500]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/products")
def api_products():
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    return jsonify([dict(p) for p in products])

# ─── SETUP / RESET LAB ─────────────────────────────────────

@app.route("/setup", methods=["GET", "POST"])
def setup():
    msg = None
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "reset":
            session.clear()
            try:
                if os.path.exists(DB):
                    os.remove(DB)
                os.system("python3 init_db.py")
                msg = "ok"
            except Exception as e:
                msg = f"error: {str(e)}"
    db = get_db()
    users_count  = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    orders_count = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    return render_template("setup.html", msg=msg,
                           users_count=users_count,
                           orders_count=orders_count)

# ─── MAIN ──────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)  # VULN A10:2025 - debug=True exposes stack trace
