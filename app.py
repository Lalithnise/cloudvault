from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import cloudinary
import cloudinary.uploader
from werkzeug.security import generate_password_hash, check_password_hash
import os
import difflib
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
app.secret_key = "supersecretkey"

cloudinary.config(
    cloud_name="dxrmvdbvd",
    api_key="898429982663349",
    api_secret="ds5JpuJqczaKpWTrsGS0aKU6P5s"
)

DB_FILE = "app.db"

# In-memory dictionary to simulate expiring links
expiring_links = {}

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                url TEXT,
                folder_name TEXT,
                folder_password TEXT
            )
        """)
    print("Database ready.")

init_db()

def get_user():
    return session.get("user")

@app.route("/")
def home():
    return render_template("landing.html")

@app.route("/ai_rename/<filename>")
def ai_rename(filename):
    new_name = "smart_" + filename.lower().replace(" ", "_")
    return {"original": filename, "suggested": new_name}

@app.route("/summary/<folder>")
def folder_summary(folder):
    return {"folder": folder, "summary": f"Folder '{folder}' contains classified digital relics."}

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if user and check_password_hash(user[2], password):
                session["user"] = username
                return redirect(url_for("dashboard"))
            flash("Invalid login.")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                flash("Account created. Please login.")
                return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not get_user():
        return redirect(url_for("login"))
    with sqlite3.connect(DB_FILE) as conn:
        files = conn.execute("SELECT * FROM files").fetchall()
    return render_template("dashboard.html", files=files)

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not get_user():
        return redirect(url_for("login"))
    if request.method == "POST":
        file = request.files["file"]
        folder_name = request.form["folder_name"]
        folder_password = request.form["folder_password"]
        if file:
            uploaded = cloudinary.uploader.upload(file)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT INTO files (filename, url, folder_name, folder_password) VALUES (?, ?, ?, ?)",
                    (file.filename, uploaded["secure_url"], folder_name, folder_password)
                )
            flash("File uploaded.")
            return redirect(url_for("dashboard"))
    return render_template("upload.html")

@app.route("/view/<int:file_id>")
def view_file(file_id):
    if not get_user():
        return redirect(url_for("login"))
    with sqlite3.connect(DB_FILE) as conn:
        file = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return render_template("view_file.html", file=file)

@app.route("/access", methods=["GET", "POST"])
def access():
    if request.method == "POST":
        folder_name = request.form["folder_name"]
        folder_password = request.form["folder_password"]
        with sqlite3.connect(DB_FILE) as conn:
            files = conn.execute(
                "SELECT * FROM files WHERE folder_name = ? AND folder_password = ?",
                (folder_name, folder_password)
            ).fetchall()
        if files:
            return render_template("dashboard.html", files=files)
        flash("Access denied.")
    return render_template("access.html")

@app.route("/search")
def search():
    query = request.args.get("q", "")
    with sqlite3.connect(DB_FILE) as conn:
        files = conn.execute("SELECT * FROM files").fetchall()
    matches = [f for f in files if query.lower() in f[1].lower() or query.lower() in f[3].lower() or difflib.SequenceMatcher(None, f[1], query).ratio() > 0.6]
    return render_template("dashboard.html", files=matches)

@app.route("/download/<int:file_id>")
def download_file(file_id):
    if not get_user():
        flash("Login required.")
        return redirect(url_for("login"))
    with sqlite3.connect(DB_FILE) as conn:
        file = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if file:
        username = session["user"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("downloads.log", "a") as log_file:
            log_file.write(f"{timestamp} - {username} downloaded {file[1]}\n")
        return redirect(file[2])
    flash("File not found.")
    return redirect(url_for("dashboard"))

@app.route("/generate_link/<int:file_id>")
def generate_link(file_id):
    if not get_user():
        return redirect(url_for("login"))
    link_id = str(uuid.uuid4())
    expiration = datetime.now() + timedelta(minutes=10)
    expiring_links[link_id] = {"file_id": file_id, "expires": expiration}
    return f"/use_link/{link_id}"

@app.route("/use_link/<link_id>", methods=["GET", "POST"])
def use_link_password(link_id):
    info = expiring_links.get(link_id)
    if not info:
        return "Link expired or invalid", 403
    if datetime.now() > info["expires"]:
        del expiring_links[link_id]
        return "Link expired", 403
    if info.get("password"):
        if request.method == "POST":
            input_password = request.form.get("password")
            if input_password != info["password"]:
                return "Incorrect password", 403
        else:
            return """
            <form method='POST'>
                <p>This link is protected. Enter password:</p>
                <input type='password' name='password' required>
                <button type='submit'>Access</button>
            </form>
            """
    with sqlite3.connect(DB_FILE) as conn:
        file = conn.execute("SELECT * FROM files WHERE id = ?", (info["file_id"],)).fetchone()
    if file:
        return redirect(file[2])
    return "File not found", 404

@app.route("/admin/logs")
def admin_logs():
    if not get_user() or session.get("user") != "admin":
        flash("Unauthorized access.")
        return redirect(url_for("dashboard"))
    if not os.path.exists("downloads.log"):
        return render_template("admin_panel.html", logs="No downloads yet.")
    with open("downloads.log", "r") as f:
        logs = f.read()
    return render_template("admin_panel.html", logs=logs)

if __name__ == "__main__":
    app.run(debug=True)