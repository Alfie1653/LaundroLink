import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import uuid
from datetime import datetime, timedelta
import urllib
from flask_wtf.csrf import CSRFProtect
from create_db import migrate
csrf = CSRFProtect()

#Run migrations on startup
migrate()


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# =========================
# REVIEW TOKENS
# =========================

def generate_review_token(provider_id):
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=2)  # link valid for 48 hours


    query_one("""
        INSERT INTO review_tokens (provider_id, token, expires_at)
        VALUES (%s, %s, %s)
    """, (provider_id, token, expires_at))


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

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.DictCursor
    )
    return conn

def query_one(sql, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return result

def query_all(sql, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    result = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return result

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# ROUTES
# =========================

# Home page
@app.route("/")
def index():
    providers = query_all("SELECT * FROM providers")
    return render_template("index.html", providers=providers)


#Register
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

        # Check if phone already exists
        existing = query_one(
            "SELECT * FROM providers WHERE phone = %s",
            (phone,)
        )
        if existing:
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

        # Insert provider
        query_one("""
            INSERT INTO providers
            (name, country_code, area, price_per_kg, delivery_fee, services,
             phone, password, profile_pic, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            name, country_code, area, price, delivery,
            services, phone, password_hash, filename, description
        ))

        flash("Laundry service registered successfully!", "success")
        return redirect(url_for("register", success=1))

    redirect_to_index = request.args.get("success") == "1"
    return render_template(
        "register_provider.html",
        redirect_to_index=redirect_to_index
    )


# -------------------------
# LOGIN
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"]
        password = request.form["password"]

        provider = query_one(
            "SELECT * FROM providers WHERE phone = %s",
            (phone,)
        )

        if provider and check_password_hash(provider["password"], password):
            session["provider_id"] = provider["id"]
            session["provider_name"] = provider["name"]
            flash("Logged in successfully!", "success")
            return redirect(
                url_for("owner_dashboard", provider_id=provider["id"])
            )
        else:
            flash("Invalid phone number or password.", "error")
            return redirect("/login")

    return render_template("login.html")


# -------------------------
# OWNER DASHBOARD
# -------------------------
@app.route("/owner_dashboard/<int:provider_id>", methods=["GET", "POST"])
def owner_dashboard(provider_id):

    # 🔐 AUTHORIZATION CHECK (CRITICAL)
    if session.get("provider_id") != provider_id:
        flash("Unauthorized access.", "error")
        return redirect("/login")

    provider = query_one(
        "SELECT * FROM providers WHERE id = %s",
        (provider_id,)
    )

    feedbacks = query_all(
        "SELECT * FROM ratings WHERE provider_id = %s ORDER BY created_at DESC",
        (provider_id,)
    )

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
        password_hash = (
            generate_password_hash(password)
            if password else provider["password"]
        )

        file = request.files.get("profile_pic")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{name.replace(' ', '_')}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(filepath)
        else:
            unique_filename = provider["profile_pic"]

        query_one("""
            UPDATE providers
            SET name=%s,
                area=%s,
                price_per_kg=%s,
                delivery_fee=%s,
                services=%s,
                phone=%s,
                country_code=%s,
                description=%s,
                profile_pic=%s,
                password=%s
            WHERE id=%s
        """, (
            name, area, price, delivery, services, phone,
            country_code, description, unique_filename,
            password_hash, provider_id
        ))

        flash("Details updated successfully!", "success")
        return redirect(url_for("owner_dashboard", provider_id=provider_id))

    return render_template(
        "owner_dashboard.html",
        provider=provider,
        feedbacks=feedbacks
    )


# -------------------------
# SERVICE PAGE
# -------------------------
@app.route("/service/<int:provider_id>", methods=["GET", "POST"])
def service_page(provider_id):

    provider = query_one(
        "SELECT * FROM providers WHERE id = %s",
        (provider_id,)
    )

    feedbacks = query_all(
        "SELECT * FROM ratings WHERE provider_id = %s ORDER BY created_at DESC",
        (provider_id,)
    )

    if not provider:
        return "Provider not found", 404

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "")

        query_one(
            "INSERT INTO ratings (provider_id, customer_name, rating, comment) "
            "VALUES (%s, %s, %s, %s)",
            (provider_id, customer_name, rating, comment)
        )

        flash("Thank you for your feedback!", "success")
        return redirect(url_for("service_page", provider_id=provider_id))

    return render_template(
        "service_page.html",
        provider=provider,
        feedbacks=feedbacks
    )


# -------------------------
# REQUEST SERVICE (WHATSAPP)
# -------------------------
@app.route("/request_service/<int:provider_id>")
def request_service(provider_id):
    print("Request Service Route Hit", provider_id)

    provider = query_one(
        "SELECT name, phone FROM providers WHERE id = %s",
        (provider_id,)
    )

    if not provider:
        flash("Laundry service not found", "error")
        return redirect("/")

    # ✅ Token generation stays unchanged
    token = generate_review_token(provider_id)

    review_link = url_for("leave_review", token=token, _external=True)

    message = (
        f"Hello {provider['name']}, I would like to request laundry service.\n\n"
        f"After the service, please leave a review here:\n{review_link}"
    )

    encoded_message = urllib.parse.quote(message)
    phone = provider["phone"].replace("+", "").replace(" ", "")
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"

    return redirect(whatsapp_url)


# -------------------------
# REVIEW PAGE
# -------------------------
@app.route("/review/<token>", methods=["GET", "POST"])
def leave_review(token):
    record = query_one(
        """
        SELECT * FROM review_tokens
        WHERE token = %s AND expires_at > %s
        """,
        (token, datetime.utcnow())
    )

    if not record:
        return "Review link invalid or expired", 403

    provider_id = record["provider_id"]

    if request.method == "POST":
        name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating"))
        comment = request.form.get("comment", "")

        # Insert review
        query_one(
            """
            INSERT INTO ratings (provider_id, customer_name, rating, comment)
            VALUES (%s, %s, %s, %s)
            """,
            (provider_id, name, rating, comment)
        )

        # Delete token after use
        query_one(
            "DELETE FROM review_tokens WHERE token = %s",
            (token,)
        )

        flash("Thank you for your review!", "success")
        return redirect(url_for("service_page", provider_id=provider_id))

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
        provider = query_one(
            "SELECT * FROM providers WHERE phone = %s",
            (phone,)
        )

        if provider:
            raw_token = secrets.token_urlsafe(32)
            token_hash = generate_password_hash(raw_token)
            expires_at = datetime.utcnow() + timedelta(minutes=5)

            # Remove old tokens
            query_one(
                "DELETE FROM password_resets WHERE provider_id = %s",
                (provider["id"],)
            )

            # Insert new token
            query_one(
                """
                INSERT INTO password_resets (provider_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (provider["id"], token_hash, expires_at)
            )

            reset_link = url_for("reset_password", token=raw_token, _external=True)

        return render_template("forgot_password.html", reset_link=reset_link)

    return render_template("forgot_password.html", reset_link=reset_link)


# -------------------------
# RESET PASSWORD
# -------------------------
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    # Fetch all non-expired reset tokens
    resets = query_all(
        "SELECT * FROM password_resets WHERE expires_at > %s",
        (datetime.utcnow(),)
    )

    match = None
    for r in resets:
        if check_password_hash(r["token_hash"], token):
            match = r
            break

    if not match:
        flash("Invalid or expired reset link.", "error")
        return redirect("/forgot-password")

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or not confirm_password:
            flash("Please fill in all fields.", "error")
            return render_template("reset_password.html")

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")

        password_hash = generate_password_hash(new_password)

        # Update provider password
        query_one(
            "UPDATE providers SET password=%s WHERE id=%s",
            (password_hash, match["provider_id"])
        )

        # Delete used reset token
        query_one(
            "DELETE FROM password_resets WHERE id=%s",
            (match["id"],)
        )

        flash("Password updated successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
