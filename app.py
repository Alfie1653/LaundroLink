import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import uuid
from datetime import datetime, timedelta
import urllib

app = Flask(__name__)
app.secret_key = os.environ.get("SECRTE_KEY", "dev_secret")

# =========================
# REVIEW TOKENS
# =========================

def generate_review_token(provider_id):
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=2)  # link valid for 48 hours

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO review_tokens (provider_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (provider_id, token, expires_at))

    conn.commit()
    conn.close()

    return token


# =========================
# CONFIGURATION
# =========================
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# DATABASE & HELPERS
# =========================
db_path = os.path.join(os.path.dirname(__file__), "laundry.db")

def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# ROUTES
# =========================

# Home page
@app.route("/")
def index():
    db = get_db_connection()
    providers = db.execute("SELECT * FROM providers").fetchall()
    db.close()
    return render_template("index.html", providers=providers)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        country_code = request.form.get("country_code", "+254")
        area = request.form["area"]
        price = request.form["price"]
        delivery = request.form["delivery"]
        services = request.form["services"]
        phone = request.form["phone"]
        password = request.form["password"]
        description = request.form.get("description", "")

        db = get_db_connection()
        existing = db.execute("SELECT * FROM providers WHERE phone = ?", (phone,)).fetchone()
        if existing:
            db.close()
            flash("This phone number is already registered.", "error")
            return redirect("/register")

        password_hash = generate_password_hash(password)

        file = request.files.get("profile_pic")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{name.replace(' ', '_')}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(filepath)
            filename = unique_filename
        else:
            filename = "profile_placeholder.png"

        db.execute("""
            INSERT INTO providers
            (name, country_code, area, price_per_kg, delivery_fee, services, phone, password, profile_pic, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, country_code, area, price, delivery, services, phone, password_hash, filename, description))
        db.commit()
        db.close()

        flash("Laundry service registered successfully!", "success")
        # Redirect with query parameter to trigger JS
        return redirect(url_for("register", success=1))

    # Check for query parameter
    redirect_to_index = request.args.get("success") == "1"
    return render_template("register_provider.html", redirect_to_index=redirect_to_index)

# -------------------------
# LOGIN
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"]
        password = request.form["password"]

        db = get_db_connection()
        provider = db.execute("SELECT * FROM providers WHERE phone = ?", (phone,)).fetchone()
        db.close()

        if provider and check_password_hash(provider["password"], password):
            session["provider_id"] = provider["id"]
            session["provider_name"] = provider["name"]
            flash("Logged in successfully!", "success")
            return redirect(url_for('owner_dashboard', provider_id=provider["id"]))
        else:
            flash("Invalid phone number or password.", "error")
            return redirect("/login")

    return render_template("login.html")

# -------------------------
# OWNER DASHBOARD
# -------------------------
@app.route("/owner_dashboard/<int:provider_id>", methods=["GET", "POST"])
def owner_dashboard(provider_id):
    db = get_db_connection()
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
    feedbacks = db.execute("SELECT * FROM ratings WHERE provider_id = ? ORDER BY created_at DESC", (provider_id,)).fetchall()
    db.close()

    if not provider:
        return "Provider not found", 404

    if request.method == "POST":
        name = request.form["name"]
        area = request.form["area"]
        price = request.form["price"]
        delivery = request.form["delivery"]
        services = request.form["services"]
        phone = request.form["phone"]
        country_code = request.form.get("country_code", "+254")
        description = request.form.get("description", "")

        password = request.form.get("password")
        password_hash = generate_password_hash(password) if password else provider["password"]

        file = request.files.get("profile_pic")
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            unique_filename = f"{name.replace(' ','_')}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(filepath)
        else:
            unique_filename = provider["profile_pic"]

        db = get_db_connection()
        db.execute("""
            UPDATE providers
            SET name=?, area=?, price_per_kg=?, delivery_fee=?, services=?, phone=?, country_code=?, description=?, profile_pic=?, password=?
            WHERE id=?
        """, (name, area, price, delivery, services, phone, country_code, description, unique_filename, password_hash, provider_id))
        db.commit()
        db.close()
        flash("Details updated successfully!", "success")
        return redirect(url_for('owner_dashboard', provider_id=provider_id))

    return render_template("owner_dashboard.html", provider=provider, feedbacks=feedbacks)

# -------------------------
# SERVICE PAGE
# -------------------------
@app.route("/service/<int:provider_id>", methods=["GET", "POST"])
def service_page(provider_id):
    db = get_db_connection()
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
    feedbacks = db.execute("SELECT * FROM ratings WHERE provider_id = ? ORDER BY created_at DESC", (provider_id,)).fetchall()
    db.close()

    if not provider:
        return "Provider not found", 404

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "")

        db = get_db_connection()
        db.execute("INSERT INTO ratings (provider_id, customer_name, rating, comment) VALUES (?, ?, ?, ?)",
                   (provider_id, customer_name, rating, comment))
        db.commit()
        db.close()
        flash("Thank you for your feedback!", "success")
        return redirect(f"/service/{provider_id}")

    return render_template("service_page.html", provider=provider, feedbacks=feedbacks)

# -------------------------
# REQUEST SERVICE (WHATSAPP)
# -------------------------
@app.route("/request_service/<int:provider_id>")
def request_service(provider_id):
    print("Request Service Route Hit", provider_id)
    conn = get_db_connection()
    provider = conn.execute(
        "SELECT name, phone FROM providers WHERE id = ?",
        (provider_id,)
    ).fetchone()
    conn.close()

    if not provider:
        flash("Laundry service not found", "error")
        return redirect("/")

    # ✅ Token IS being generated (this part is fine)
    token = generate_review_token(provider_id)

    review_link = url_for("leave_review", token=token, _external=True)

    message = (
        f"Hello {provider['name']}, I would like to request laundry service.\n\n"
        f"After the service, please leave a review here:\n{review_link}"
    )

    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{provider['phone']}?text={encoded_message}"

    return redirect(whatsapp_url)

# -------------------------
# REVIEW PAGE
# -------------------------
@app.route("/review/<token>", methods=["GET", "POST"])
def leave_review(token):
    db = get_db_connection()

    record = db.execute("""
        SELECT * FROM review_tokens
        WHERE token = ? AND expires_at > ?
    """, (token, datetime.utcnow())).fetchone()

    if not record:
        db.close()
        return "Review link invalid or expired", 403

    provider_id = record["provider_id"]

    if request.method == "POST":
        name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating"))
        comment = request.form.get("comment", "")

        db.execute("""
            INSERT INTO ratings (provider_id, customer_name, rating, comment)
            VALUES (?, ?, ?, ?)
        """, (provider_id, name, rating, comment))

        db.execute("DELETE FROM review_tokens WHERE token = ?", (token,))
        db.commit()
        db.close()

        flash("Thank you for your review!", "success")
        return redirect(url_for("service_page", provider_id=provider_id))

    db.close()
    return render_template("leave_review.html")


# -------------------------
# LOGOUT
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect("/")

# -------------------------
# FORGOT PASSWORD
# -------------------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_link = None

    if request.method == "POST":
        phone = request.form.get("phone")
        db = get_db_connection()
        provider = db.execute("SELECT * FROM providers WHERE phone = ?", (phone,)).fetchone()

        if provider:
            raw_token = secrets.token_urlsafe(32)
            token_hash = generate_password_hash(raw_token)
            expires_at = datetime.utcnow() + timedelta(minutes=5)

            # Remove old tokens
            db.execute("DELETE FROM password_resets WHERE provider_id = ?", (provider["id"],))
            db.execute("""INSERT INTO password_resets (provider_id, token_hash, expires_at)
                          VALUES (?, ?, ?)""", (provider["id"], token_hash, expires_at))
            db.commit()

            reset_link = url_for("reset_password", token=raw_token, _external=True)

        db.close()
        return render_template("forgot_password.html", reset_link=reset_link)

    return render_template("forgot_password.html", reset_link=reset_link)

# -------------------------
# RESET PASSWORD
# -------------------------
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    db = get_db_connection()
    resets = db.execute("""
        SELECT * FROM password_resets
        WHERE expires_at > ?
    """, (datetime.utcnow(),)).fetchall()

    match = None
    for r in resets:
        if check_password_hash(r["token_hash"], token):
            match = r
            break

    if not match:
        flash("Invalid or expired reset link.", "error")
        db.close()
        return redirect("/forgot-password")

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or not confirm_password:
            flash("Please fill in all fields.", "error")
            db.close()
            return render_template("reset_password.html")

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            db.close()
            return render_template("reset_password.html")

        password_hash = generate_password_hash(new_password)

        db.execute("UPDATE providers SET password=? WHERE id=?", (password_hash, match["provider_id"]))
        db.execute("DELETE FROM password_resets WHERE id=?", (match["id"],))
        db.commit()
        db.close()

        flash("Password updated successfully! You can now log in.", "success")
        # Redirect to login page
        return redirect(url_for("login"))

    db.close()
    return render_template("reset_password.html")

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(debug=True)
