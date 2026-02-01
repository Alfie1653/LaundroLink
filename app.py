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

from supabase_client import supabase
from dotenv import load_dotenv


load_dotenv()
csrf = CSRFProtect()

#Run migrations on startup
#migrate()


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

csrf.init_app(app)
# =========================
# REVIEW TOKENS
# =========================

def generate_review_token(provider_id):
    token = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(days=2)).isoformat()  # link valid for 48 hours


    supabase.table("review_tokens").insert({
        "provider_id": provider_id,
        "token": token,
        "expires_at": expires_at
    }).execute()


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

def execute(sql, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# ROUTES
# =========================

# -------------------------
# HOME PAGE
# -------------------------
@app.route("/", methods=["GET"])
def home():
    sort_by = request.args.get("sort", "date")  # default is date

    # Fetch all providers
    res_providers = supabase.table("providers").select("*").execute()
    providers = res_providers.data

    # Fetch all ratings once (so we can always calculate avg_rating and num_reviews)
    res_ratings = supabase.table("ratings").select("*").execute()
    ratings = res_ratings.data

    # Map provider_id -> list of ratings
    ratings_map = {}
    for r in ratings:
        ratings_map.setdefault(r['provider_id'], []).append(r['rating'])

    # Compute avg_rating and number of reviews for each provider
    for p in providers:
        p_ratings = ratings_map.get(p['id'], [])
        if p_ratings:
            p['avg_rating'] = round(sum(p_ratings) / len(p_ratings), 1)
            p['num_reviews'] = len(p_ratings)
        else:
            p['avg_rating'] = 0
            p['num_reviews'] = 0

    # Sorting
    if sort_by == "rating":
        providers_sorted = sorted(providers, key=lambda x: x['avg_rating'], reverse=True)
    elif sort_by == "alphabetical":
        providers_sorted = sorted(providers, key=lambda x: x['name'].lower())
    else:  # default "date"
        providers_sorted = sorted(providers, key=lambda x: x['created_at'], reverse=True)

    return render_template("index.html", providers=providers_sorted, sort_by=sort_by)

# -------------------------
# REGISTER
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        country_code = request.form.get("country_code", "+254")
        area = request.form["area"]
        price = float(request.form["price"])
        delivery = float(request.form["delivery"])

        services = request.form.getlist("services")
        services = ", ".join(services)

        phone = request.form["phone"]
        password = request.form["password"]
        description = request.form.get("description", "")

        # Check if phone already exists
        res = supabase.table("providers").select("*").eq("phone", phone).execute()
        existing = res.data

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
        data = {
            "name": name,
            "country_code": country_code,
            "area": area,
            "price_per_kg": price,
            "delivery_fee": delivery,
            "services": services,
            "phone": phone,
            "password": password_hash,
            "description": description,
            "profile_pic": filename
        }
    
        res = supabase.table("providers").insert(data).execute()

        provider = res.data[0]
        provider_id = provider["id"]

        session["provider_id"] = provider_id
        session["provider_name"] = provider["name"]

        return render_template(
            "register_provider.html",
            show_success=True,
            redirect_url=url_for("owner_dashboard", provider_id=provider_id)
        )

    return render_template("register_provider.html", show_success=False)


# -------------------------
# LOGIN
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"]
        password = request.form["password"]

        res = supabase.table("providers").select("*").eq("phone", phone).execute()
        provider = res.data[0] if res.data else None

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

    res = supabase.table("providers").select("*").eq("id", provider_id).execute()
    provider = res.data[0] if res.data else None

    res = supabase.table("ratings").select("*").eq("provider_id", provider_id).order("created_at", desc=True).execute()
    feedbacks = res.data

    if not provider:
        return "Provider not found", 404

    if request.method == "POST":
        name = request.form["name"]
        area = request.form["area"]
        price = request.form["price"]
        delivery = request.form["delivery"]
        services = request.form.getlist("services")
        services = ", ".join(services)
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

        supabase.table("providers").update({
            "name": name,
            "area": area,
            "price_per_kg": price,
            "delivery_fee": delivery,
            "services": services,
            "phone": phone,
            "country_code": country_code,
            "description": description,
            "profile_pic": unique_filename,
            "password": password_hash
        }).eq("id", provider_id).execute()
    

        flash("Details updated successfully!", "success")
        return redirect(url_for("owner_dashboard", provider_id=provider_id))

    # ===== Convert stored service values to readable labels =====
    service_map = {
        "wash_fold": "Wash & Fold",
        "wash_iron": "Wash & Iron",
        "ironing_only": "Ironing Only",
        "bedding_duvet": "Bedding & Duvet Cleaning",
        "curtains": "Curtains Cleaning",
        "carpet": "Carpet Cleaning",
        "shoes": "Shoes Cleaning",
        "leather": "Leather Garments Cleaning",
        "dry_cleaning": "Dry Cleaning",
        "stain_removal": "Stain Removal"
    }

    services_values = provider["services"].split(",") if provider["services"] else []
    services_labels = [service_map.get(s.strip(), s.strip()) for s in services_values]
    provider["services_display"] = ", ".join(services_labels)

    # Render template
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

    res = supabase.table("providers").select("*").eq("id", provider_id).execute()
    provider = res.data[0] if res.data else None

    # Convert services to comma-separated string
    services = provider.get("services", "")
    if isinstance(services, list):
        # If it's already a list, join with comma
        provider["services_str"] = ", ".join(services)
    else:
        # It's a string, use as-is
        provider["services_str"] = services

    res = supabase.table("ratings").select("*").eq("provider_id", provider_id).order("created_at", desc=True).limit(1).execute()
    feedbacks = res.data

    if not provider:
        return "Provider not found", 404

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "")

        supabase.table("ratings").insert({
            "provider_id": provider_id,
            "customer_name": customer_name,
            "rating": rating,
            "comment": comment
        }).execute()

        flash("Thank you for your feedback!", "success")
        return redirect(url_for("service_page", provider_id=provider_id))

    return render_template(
        "service_page.html",
        provider=provider,
        feedbacks=feedbacks
    )


# -------------------------
# ALL CUSTOMER REVIEWS
# -------------------------
@app.route("/reviews/<int:provider_id>")
def all_reviews(provider_id):
    # Fetch all reviews
    res = (
        supabase.table("ratings")
        .select("*")
        .eq("provider_id", provider_id)
        .order("created_at", desc=True)
        .execute()
    )
    feedbacks = res.data

    # Fetch provider info
    res2 = supabase.table("providers").select("*").eq("id", provider_id).execute()
    provider = res2.data[0] if res2.data else None

    if not provider:
        return "Provider not found", 404

    return render_template(
        "all_reviews.html",
        provider=provider,
        feedbacks=feedbacks
    )


# -------------------------
# REQUEST SERVICE (WHATSAPP)
# -------------------------
@app.route("/request_service/<int:provider_id>")
def request_service(provider_id):
    print("Request Service Route Hit", provider_id)

    res = supabase.table("providers").select("name, phone").eq("id", provider_id).execute()
    provider = res.data[0] if res.data else None

    if not provider:
        flash("Laundry service not found", "error")
        return redirect("/")

    # ✅ Token generation stays unchanged
    token = generate_review_token(provider_id)

    review_link = url_for("leave_review", token=token, _external=True)

    message = (
        f"Hi {provider['name']}! \n"
        f"I found your service on LaundroLink and would like to request laundry service.\n\n"
        f"Could you please let me know your availability and pickup details? Thanks!"

        f"After the service, I will leave you a review:\n{review_link}"
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
    res = supabase.table("review_tokens") \
    .select("*") \
    .eq("token", token) \
    .filter("expires_at", "gt", datetime.utcnow().isoformat()) \
    .execute()

    record = res.data[0] if res.data else None

    if not record:
        return "Review link invalid or expired", 403

    provider_id = record["provider_id"]

    if request.method == "POST":
        name = request.form.get("customer_name", "Anonymous")
        rating = int(request.form.get("rating"))
        comment = request.form.get("comment", "")

        # Insert review
        supabase.table("ratings").insert({
            "provider_id": provider_id,
            "customer_name": name,
            "rating": rating,
            "comment": comment
        }).execute()

        # Delete token after use
        supabase.table("review_tokens").delete().eq("token", token).execute()

        return render_template("leave_review.html", show_thank_you=True, redirect_url=url_for("service_page", provider_id=provider_id))

    return render_template("leave_review.html", show_thank_you=False)


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

        res = supabase.table("providers").select("*").eq("phone", phone).execute()
        provider = res.data[0] if res.data else None

        if provider:
            raw_token = secrets.token_urlsafe(32)
            token_hash = generate_password_hash(raw_token)
            expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat()

            # Remove old tokens
            supabase.table("password_resets").delete().eq("provider_id", provider["id"]).execute()

            # Insert new token
            supabase.table("password_resets").insert({
                "provider_id": provider["id"],
                "token_hash": token_hash,
                "expires_at": expires_at
            }).execute()

            reset_link = url_for("reset_password", token=raw_token, _external=True)

        return render_template("forgot_password.html", reset_link=reset_link)

    return render_template("forgot_password.html", reset_link=reset_link)


# -------------------------
# RESET PASSWORD
# -------------------------
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    # Fetch all non-expired reset tokens
    resets = supabase.table("password_resets").select("*").filter("expires_at", "gt", datetime.utcnow()).execute().data

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
        supabase.table("providers").update({
            "password": password_hash
        }).eq("id", match["provider_id"]).execute()

        # Delete used reset token
        supabase.table("password_resets").delete().eq("id", match["id"]).execute()

        flash("Password updated successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
