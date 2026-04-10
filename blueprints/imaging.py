import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from extensions import send_email

imaging_bp = Blueprint("imaging", __name__)


@imaging_bp.route("/list")
def list_view():
    """Public list of ongoing and waiting imaging slots."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.execute("SELECT * FROM bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("list.html", ongoing_slots=ongoing, waiting_slots=waiting)


def register_imaging(user_name, pi_name, email, origin, esm, sample_name, grids, days):
    """
    Insert a new imaging booking.
    Returns (success: bool, message: str).
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM bookings WHERE email=%s AND status IN ('waiting','ongoing')",
        [email],
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        return False, "This email is already registered for an Imaging slot."

    cur.execute(
        """INSERT INTO bookings
           (user_name, pi_name, email, origin, esm, sample_name,
            grids, days, registration_date, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'waiting')""",
        (user_name, pi_name, email, origin, esm, sample_name,
         grids, days, datetime.date.today()),
    )
    conn.commit()
    cur.close()
    conn.close()

    send_email(
        email,
        "Cryo-EM Imaging Slot Registered",
        (
            f"Dear {user_name},\n\n"
            f"Your Imaging slot has been registered.\n"
            f"PI: {pi_name}\nSample: {sample_name}\n"
            f"Grids: {grids}\nDays: {days}\n\n"
            f"Cryo-EM Team"
        ),
    )
    return True, "Imaging slot registered successfully."
