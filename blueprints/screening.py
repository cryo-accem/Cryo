import datetime
from flask import Blueprint, render_template
from database import get_db
from extensions import send_email

screening_bp = Blueprint("screening", __name__)


@screening_bp.route("/screening")
def screening_list():
    """Public list of ongoing and waiting screening slots."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM screening_bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.execute("SELECT * FROM screening_bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("screening_list.html", ongoing_slots=ongoing, waiting_slots=waiting)


def register_screening(user_name, pi_name, email, origin, esm, sample_name, grids, days):
    """
    Insert a new screening booking.
    Returns (success: bool, message: str).
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM screening_bookings WHERE email=%s AND status IN ('waiting','ongoing')",
        [email],
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        return False, "This email is already registered for a Screening slot."

    cur.execute(
        """INSERT INTO screening_bookings
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
        "Cryo-EM Screening Slot Registered",
        (
            f"Dear {user_name},\n\n"
            f"Your Screening slot has been registered.\n"
            f"PI: {pi_name}\nSample: {sample_name}\n"
            f"Grids: {grids}\nDays: {days}\n\n"
            f"Cryo-EM Team"
        ),
    )
    return True, "Screening slot registered successfully."
