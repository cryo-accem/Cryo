import datetime
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash,
)
from werkzeug.security import check_password_hash
from database import get_db
from extensions import send_email

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_ALLOWED_ADMIN_ENDPOINTS = {
    "admin.panel",
    "admin.logout",
    "admin.datacollecting",
    "admin.load_dc",
    "admin.complete_dc",
    "admin.delete_dc",
    "admin.freezing_admin",
    "admin.screening_admin",
    "admin.load_sc",
    "admin.complete_sc",
    "admin.delete_sc",
    "admin.history",
    "static",
}


# ── Session guard ────────────────────────────────────────────────────────────

@admin_bp.before_app_request
def check_admin_session():
    if "admin_logged_in" in session and request.endpoint:
        if request.endpoint not in _ALLOWED_ADMIN_ENDPOINTS:
            session.pop("admin_logged_in", None)


# ── Login / Logout ───────────────────────────────────────────────────────────

@admin_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", [username])
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.permanent = True
            session["admin_logged_in"] = True
            return redirect(url_for("admin.panel"))

        flash("Invalid username or password.")
    return render_template("admin.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("public.index"))


# ── Main Dashboard ───────────────────────────────────────────────────────────

@admin_bp.route("/panel")
def panel():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    return render_template("admin_panel.html")


# ── Data Collecting Section ──────────────────────────────────────────────────

@admin_bp.route("/datacollecting")
def datacollecting():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.execute("SELECT * FROM bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "admin_datacollecting.html",
        waiting_registrations=waiting,
        ongoing_registrations=ongoing,
    )


@admin_bp.route("/datacollecting/load/<int:booking_id>")
def load_dc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE bookings SET status='ongoing' WHERE id=%s", [booking_id])
    cur.execute("SELECT * FROM bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if reg:
        send_email(
            reg["email"],
            "Cryo-EM Data Collecting Slot Loaded",
            f"Dear {reg['user_name']},\n\nYour grids are loaded today.\n\nCryo-EM Team",
        )
    return redirect(url_for("admin.datacollecting"))


@admin_bp.route("/datacollecting/complete/<int:booking_id>")
def complete_dc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE bookings SET status='completed', completion_date=%s WHERE id=%s",
        (datetime.date.today(), booking_id),
    )
    cur.execute("SELECT * FROM bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if reg:
        send_email(
            reg["email"],
            "Cryo-EM Data Collecting Slot Completed",
            (
                f"Dear {reg['user_name']},\n\n"
                f"Your data collecting slot is completed. Kindly collect your data.\n\n"
                f"Cryo-EM Team"
            ),
        )
    return redirect(url_for("admin.datacollecting"))


@admin_bp.route("/datacollecting/delete/<int:booking_id>")
def delete_dc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("DELETE FROM bookings WHERE id=%s", [booking_id])
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("admin.datacollecting"))


# ── Freezing Section ─────────────────────────────────────────────────────────

@admin_bp.route("/freezing")
def freezing_admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    today = datetime.date.today()

    cur.execute(
        "SELECT * FROM freezing_bookings WHERE freezing_date < %s AND status='active'",
        [today],
    )
    expired = cur.fetchall()

    for e in expired:
        cur.execute(
            """INSERT INTO completed_freezing
               (user_name, pi_name, email, origin, sample_name, grids, freezing_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (e["user_name"], e["pi_name"], e["email"],
             e["origin"], e["sample_name"], e["grids"], e["freezing_date"]),
        )
        cur.execute(
            "UPDATE freezing_bookings SET status='completed' WHERE id=%s", [e["id"]]
        )
        send_email(
            e["email"],
            "Cryo-EM Freezing Completed",
            f"Dear {e['user_name']},\n\nYour freezing on {e['freezing_date']} is completed.\n\nCryo-EM Team",
        )

    cur.execute("SELECT * FROM freezing_bookings WHERE status='active'")
    active = cur.fetchall()
    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed = cur.fetchall()

    conn.commit()
    cur.close()
    conn.close()

    return render_template(
        "admin_freezing.html", active_slots=active, completed_slots=completed
    )


# ── Screening Section ────────────────────────────────────────────────────────

@admin_bp.route("/screening")
def screening_admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM screening_bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.execute("SELECT * FROM screening_bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "admin_screening.html",
        waiting_registrations=waiting,
        ongoing_registrations=ongoing,
    )


@admin_bp.route("/screening/load/<int:booking_id>")
def load_sc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE screening_bookings SET status='ongoing' WHERE id=%s", [booking_id])
    cur.execute("SELECT * FROM screening_bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if reg:
        send_email(
            reg["email"],
            "Cryo-EM Screening Slot Loaded",
            f"Dear {reg['user_name']},\n\nYour screening grids are loaded today.\n\nCryo-EM Team",
        )
    return redirect(url_for("admin.screening_admin"))


@admin_bp.route("/screening/complete/<int:booking_id>")
def complete_sc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE screening_bookings SET status='completed', completion_date=%s WHERE id=%s",
        (datetime.date.today(), booking_id),
    )
    cur.execute("SELECT * FROM screening_bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if reg:
        send_email(
            reg["email"],
            "Cryo-EM Screening Slot Completed",
            (
                f"Dear {reg['user_name']},\n\n"
                f"Your screening slot is completed. Kindly collect your data.\n\n"
                f"Cryo-EM Team"
            ),
        )
    return redirect(url_for("admin.screening_admin"))


@admin_bp.route("/screening/delete/<int:booking_id>")
def delete_sc(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("DELETE FROM screening_bookings WHERE id=%s", [booking_id])
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("admin.screening_admin"))


# ── History ──────────────────────────────────────────────────────────────────

@admin_bp.route("/history")
def history():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "SELECT * FROM bookings WHERE status='completed' ORDER BY completion_date DESC"
    )
    completed_imaging = cur.fetchall()
    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed_freezing = cur.fetchall()
    cur.execute(
        "SELECT * FROM screening_bookings WHERE status='completed' ORDER BY completion_date DESC"
    )
    completed_screening = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "history.html",
        completed_imaging=completed_imaging,
        completed_freezing=completed_freezing,
        completed_screening=completed_screening,
    )
