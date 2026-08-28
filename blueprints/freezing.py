import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from extensions import send_email
from revenue import FREEZING_RATE

freezing_bp = Blueprint("freezing", __name__)

GRID_LIMIT_PER_DAY = 8


def complete_freezing_booking(cur, booking_id, actual_grids):
    """Complete one freezing booking using the grids actually frozen."""
    cur.execute(
        "SELECT * FROM freezing_bookings WHERE id=? AND status='active'",
        [booking_id],
    )
    booking = cur.fetchone()
    if not booking:
        return None
    freezing_charge = FREEZING_RATE * actual_grids
    cur.execute(
        """INSERT INTO completed_freezing
           (user_name, pi_name, email, origin, sample_name, grids, freezing_date,
            actual_grids, slot_charge, freezing_charge, clipping_charge,
            processing_charge, gst_amount, total_billed, processing_requested)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, 0)""",
        (booking["user_name"], booking["pi_name"], booking["email"],
         booking["origin"], booking["sample_name"], booking["grids"],
         booking["freezing_date"], actual_grids, 0, freezing_charge,
         freezing_charge),
    )
    cur.execute(
        "UPDATE freezing_bookings SET status='completed' WHERE id=?",
        [booking_id],
    )
    return booking


@freezing_bp.route("/freezing_schedule")
def freezing_schedule():
    """
    Auto-expire past active freezing slots → completed_freezing,
    then render active + completed lists.
    """
    conn = get_db()
    cur = conn.cursor()
    today = datetime.date.today()

    cur.execute("SELECT * FROM freezing_bookings WHERE status='active'")
    active = cur.fetchall()

    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed = cur.fetchall()

    conn.commit()
    cur.close()
    conn.close()

    return render_template(
        "freezingschedule.html", active_slots=active, completed_slots=completed
    )


def register_freezing(user_name, pi_name, email, origin, sample_name, grids, freezing_date):
    """
    Insert a new freezing booking after checking the daily grid cap.
    Returns (success: bool, message: str).
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COALESCE(SUM(grids),0) AS total FROM freezing_bookings "
        "WHERE freezing_date=? AND status='active'",
        [freezing_date],
    )
    total = cur.fetchone()["total"]

    if total + grids > GRID_LIMIT_PER_DAY:
        remaining = GRID_LIMIT_PER_DAY - total
        cur.close()
        conn.close()
        return False, f"Grid limit exceeded. Only {remaining} grids left for this date."

    cur.execute(
        """INSERT INTO freezing_bookings
           (user_name, pi_name, email, origin, sample_name,
            grids, freezing_date, status, registered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)""",
        (user_name, pi_name, email, origin, sample_name, grids, freezing_date),
    )
    conn.commit()
    cur.close()
    conn.close()

    send_email(
        email,
        "Cryo-EM Freezing Slot Registered",
        (
            f"Dear {user_name},\n\n"
            f"Your Freezing slot has been registered.\n"
            f"PI: {pi_name}\nSample: {sample_name}\n"
            f"Grids: {grids}\nDate: {freezing_date}\n\n"
            f"Cryo-EM Team"
        ),
    )
    return True, "Freezing slot registered successfully."
