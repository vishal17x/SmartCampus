
import os
import sqlite3
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")
DB = Path(__file__).with_name("database.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id)
    )""")
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if admin_email and admin_password:
        admin = conn.execute(
            "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1"
        ).fetchone()

        if admin:
            conn.execute(
                "UPDATE users SET name=?, email=?, password=? WHERE id=?",
                ("Administrator", admin_email, admin_password, admin["id"])
            )
        else:
            conn.execute(
                "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                ("Administrator", admin_email, admin_password, "admin")
            )
    conn.commit()
    conn.close()

# Initialize the database when Gunicorn/Render starts the app
init_db()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        try:
            conn = get_db()
            conn.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                         (name,email,password))
            conn.commit()
            conn.close()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=? AND password=?",
                            (email,password)).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("admin" if user["role"] == "admin" else "student"))
        flash("Invalid email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/student", methods=["GET","POST"])
def student():
    if session.get("role") != "student":
        return redirect(url_for("login"))
    conn = get_db()
    if request.method == "POST":
        conn.execute("""INSERT INTO complaints
            (student_id,category,title,description,location,status,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (session["user_id"], request.form["category"], request.form["title"],
             request.form["description"], request.form["location"], "Pending",
             datetime.now().strftime("%d-%m-%Y %I:%M %p")))
        conn.commit()
        flash("Complaint submitted successfully.")
    complaints = conn.execute(
        "SELECT * FROM complaints WHERE student_id=? ORDER BY id DESC",
        (session["user_id"],)).fetchall()
    conn.close()
    return render_template("student.html", complaints=complaints)

@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    complaints = conn.execute("""SELECT complaints.*, users.name AS student_name,
                                 users.email AS student_email
                                 FROM complaints JOIN users ON users.id=complaints.student_id
                                 ORDER BY complaints.id DESC""").fetchall()
    total = conn.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) c FROM complaints WHERE status='Pending'").fetchone()["c"]
    progress = conn.execute("SELECT COUNT(*) c FROM complaints WHERE status='In Progress'").fetchone()["c"]
    resolved = conn.execute("SELECT COUNT(*) c FROM complaints WHERE status='Resolved'").fetchone()["c"]
    conn.close()
    return render_template("admin.html", complaints=complaints, total=total,
                           pending=pending, progress=progress, resolved=resolved)

@app.route("/update/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    status = request.form["status"]
    conn = get_db()
    conn.execute("UPDATE complaints SET status=? WHERE id=?", (status, complaint_id))
    conn.commit()
    conn.close()
    flash("Complaint status updated.")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)
