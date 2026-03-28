from flask import Flask, render_template, request, redirect, session
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

# ================= BAZA =================
def get_db():
    conn = sqlite3.connect("cars.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        car TEXT,
        car_folder TEXT,
        city TEXT,
        date_from TEXT,
        date_to TEXT,
        days INTEGER,
        price_per_day REAL,
        total_price REAL,
        status TEXT DEFAULT 'V obdelavi',
        rating INTEGER,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reservation_id INTEGER,
        sender TEXT,
        text TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contact_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        message TEXT,
        reply TEXT,
        created_at TEXT
    )
    """)

    # admin uporabnik
    cur.execute("SELECT * FROM users WHERE email = ?", ("admin@gmail.com",))
    admin = cur.fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (email, password, is_admin) VALUES (?, ?, ?)",
            ("admin@gmail.com", "admin123", 1)
        )

    conn.commit()
    conn.close()

init_db()

# ================= GLOBALNI PODATKI V TEMPLATE =================
@app.context_processor
def inject_user():
    return {
        "user": session.get("user"),
        "admin": session.get("admin")
    }

# ================= STRANI =================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/models")
def models():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT car, date_from, date_to, status
        FROM reservations
        WHERE status = 'Potrjeno'
    """)
    approved_reservations = [dict(row) for row in cur.fetchall()]

    conn.close()

    return render_template(
        "models.html",
        approved_reservations=approved_reservations
    )

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    success = None
    error = None
    user_messages = []

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            error = "Izpolni vsa polja."
        else:
            cur.execute("""
                INSERT INTO contact_messages (name, email, message, reply, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, email, message, "", datetime.utcnow().isoformat()))
            conn.commit()
            success = "Sporočilo je bilo uspešno poslano. Kontaktirali vas bomo v najkrajšem možnem času."

    if session.get("user"):
        cur.execute("""
            SELECT * FROM contact_messages
            WHERE email = ?
            ORDER BY id DESC
        """, (session.get("user"),))
        user_messages = cur.fetchall()

    conn.close()

    return render_template(
        "contact.html",
        success=success,
        error=error,
        user_messages=user_messages
    )

@app.route("/car")
def car():
    return render_template("car.html")

# ================= REGISTER =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("register.html", error="Vnesi email in geslo")

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (email, password, is_admin) VALUES (?, ?, ?)",
                (email, password, 0)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template("register.html", error="Uporabnik s tem emailom že obstaja")

        conn.close()
        session.clear()
        session["user"] = email
        return redirect("/")

    return render_template("register.html")

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        )
        user = cur.fetchone()
        conn.close()

        if not user:
            return render_template("login.html", error="Nepravilen email ali geslo")

        session.clear()

        if user["is_admin"] == 1:
            session["admin"] = True
            session["user"] = user["email"]
            return redirect("/admin")

        session["user"] = user["email"]
        return redirect("/")

    return render_template("login.html")

# ================= REZERVACIJA =================
@app.route("/reserve", methods=["POST"])
def reserve():
    if not session.get("user"):
        return redirect("/login")

    user_email = session["user"]
    car = request.form.get("car")
    car_folder = request.form.get("car_folder")
    city = request.form.get("city")
    date_from = request.form.get("from")
    date_to = request.form.get("to")
    price_per_day = request.form.get("price_per_day", "0")

    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()

        if d_to < d_from:
            return redirect("/car?car=" + car + "&error=invalid_dates")

        days = (d_to - d_from).days + 1
    except Exception:
        return redirect("/car?car=" + car + "&error=invalid_dates")

    try:
        pd = float(price_per_day)
    except Exception:
        pd = 0.0

    total_price = round(pd * days, 2)

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM reservations
        WHERE car = ?
        AND status = 'Potrjeno'
        AND NOT (date_to < ? OR date_from > ?)
    """, (car, date_from, date_to))

    existing_booking = cur.fetchone()
    if existing_booking:
        conn.close()
        return redirect("/car?car=" + car + "&error=already_booked")

    cur.execute("""
        INSERT INTO reservations
        (user_email, car, car_folder, city, date_from, date_to, days, price_per_day, total_price, status, rating, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_email,
        car,
        car_folder,
        city,
        date_from,
        date_to,
        days,
        pd,
        total_price,
        "V obdelavi",
        None,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()

    return redirect("/profile")

# ================= PROFIL =================
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not session.get("user"):
        return redirect("/login")

    user_email = session["user"]
    message = None
    error = None

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        reservation_id = request.form.get("reservation_id")

        if action == "cancel":
            try:
                cur.execute(
                    "DELETE FROM reservations WHERE id = ? AND user_email = ?",
                    (reservation_id, user_email)
                )
                conn.commit()
                message = "Rezervacija je bila preklicana."
            except Exception:
                error = "Napaka pri preklicu rezervacije."

        elif action == "send_message":
            text = request.form.get("message", "").strip()
            try:
                if text:
                    cur.execute(
                        "INSERT INTO messages (reservation_id, sender, text) VALUES (?, ?, ?)",
                        (reservation_id, "user", text)
                    )
                    conn.commit()
                    message = "Sporočilo poslano."
                else:
                    error = "Sporočilo ne sme biti prazno."
            except Exception:
                error = "Napaka pri pošiljanju sporočila."

        elif action == "rate":
            rating = request.form.get("rating")
            try:
                rating_int = int(rating)
                if rating_int < 1 or rating_int > 5:
                    raise ValueError

                cur.execute(
                    "UPDATE reservations SET rating = ? WHERE id = ? AND user_email = ?",
                    (rating_int, reservation_id, user_email)
                )
                conn.commit()
                message = "Hvala za oceno."
            except Exception:
                error = "Napaka pri ocenjevanju."

    cur.execute(
        "SELECT * FROM reservations WHERE user_email = ? ORDER BY id DESC",
        (user_email,)
    )
    reservations = cur.fetchall()

    reservations_with_messages = []
    for r in reservations:
        cur.execute(
            "SELECT * FROM messages WHERE reservation_id = ? ORDER BY id ASC",
            (r["id"],)
        )
        msgs = cur.fetchall()

        reservations_with_messages.append({
            "id": r["id"],
            "car": r["car"],
            "car_folder": r["car_folder"],
            "city": r["city"],
            "from": r["date_from"],
            "to": r["date_to"],
            "days": r["days"],
            "price_per_day": r["price_per_day"],
            "total_price": r["total_price"],
            "status": r["status"],
            "rating": r["rating"],
            "messages": msgs
        })

    conn.close()

    return render_template(
        "profile.html",
        user=user_email,
        reservations=reservations_with_messages,
        message=message,
        error=error
    )

# ================= ADMIN =================
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if not session.get("admin"):
        return redirect("/login")

    message = None
    error = None

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        reservation_id = request.form.get("reservation_id")

        try:
            if action == "approve":
                cur.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    ("Potrjeno", reservation_id)
                )
                conn.commit()
                message = "Rezervacija je bila potrjena."

            elif action == "reject":
                cur.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    ("Zavrnjeno", reservation_id)
                )
                conn.commit()
                message = "Rezervacija je bila zavrnjena."

            elif action == "reply":
                reply_text = request.form.get("reply", "").strip()
                if reply_text:
                    cur.execute(
                        "INSERT INTO messages (reservation_id, sender, text) VALUES (?, ?, ?)",
                        (reservation_id, "admin", reply_text)
                    )
                    conn.commit()
                    message = "Odgovor je bil poslan."
                else:
                    error = "Odgovor ne sme biti prazen."

            elif action == "reply_contact":
                contact_id = request.form.get("contact_id")
                reply_text = request.form.get("reply_text", "").strip()

                if reply_text:
                    cur.execute("""
                        UPDATE contact_messages
                        SET reply = ?
                        WHERE id = ?
                    """, (reply_text, contact_id))
                    conn.commit()
                    message = "Odgovor na kontaktno sporočilo je bil shranjen."
                else:
                    error = "Odgovor ne sme biti prazen."

        except Exception:
            error = "Napaka pri obdelavi zahtevka."

    cur.execute("SELECT * FROM users ORDER BY id DESC")
    users = cur.fetchall()

    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    reservations = cur.fetchall()

    reservations_with_messages = []
    for r in reservations:
        cur.execute(
            "SELECT * FROM messages WHERE reservation_id = ? ORDER BY id ASC",
            (r["id"],)
        )
        msgs = cur.fetchall()

        reservations_with_messages.append({
            "id": r["id"],
            "user": r["user_email"],
            "car": r["car"],
            "car_folder": r["car_folder"],
            "city": r["city"],
            "from": r["date_from"],
            "to": r["date_to"],
            "days": r["days"],
            "price_per_day": r["price_per_day"],
            "total_price": r["total_price"],
            "status": r["status"],
            "rating": r["rating"],
            "messages": msgs
        })

    cur.execute("SELECT * FROM contact_messages ORDER BY id DESC")
    contact_messages = cur.fetchall()

    # statistika
    cur.execute("SELECT COUNT(*) AS total FROM reservations")
    total_reservations = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'Potrjeno'")
    approved = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'Zavrnjeno'")
    rejected = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'V obdelavi'")
    pending = cur.fetchone()["total"]

    cur.execute("SELECT COALESCE(SUM(total_price), 0) AS income FROM reservations WHERE status = 'Potrjeno'")
    total_income = cur.fetchone()["income"]

    cur.execute("SELECT COUNT(*) AS total FROM users WHERE is_admin = 0")
    total_users = cur.fetchone()["total"]

    cur.execute("""
        SELECT car, COUNT(*) AS total
        FROM reservations
        GROUP BY car
        ORDER BY total DESC
        LIMIT 1
    """)
    top_car_row = cur.fetchone()
    top_car = top_car_row["car"] if top_car_row else "Ni podatkov"

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        reservations=reservations_with_messages,
        contact_messages=contact_messages,
        message=message,
        error=error,
        total_reservations=total_reservations,
        approved=approved,
        rejected=rejected,
        pending=pending,
        total_income=total_income,
        total_users=total_users,
        top_car=top_car
    )

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)