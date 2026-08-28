import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from extensions import send_email

freezing_bp = Blueprint("freezing", __name__)

GRID_LIMIT_PER_DAY = 8


@freezing_bp.route("/freezing_schedule")
def freezing_schedule():
    """
    Auto-expire past active freezing slots → completed_freezing,
    then render active + completed lists.
    """
    conn = get_db()
    cur = conn.cursor()
    today = datetime.date.today()

    # Move expired bookings to completed_freezing
    cur.execute(
        "SELECT * FROM freezing_bookings WHERE freezing_date < ? AND status='active'",
        [today],
    )
    expired = cur.fetchall()

    for e in expired:
        cur.execute(
            """INSERT INTO completed_freezing
               (user_name, pi_name, email, origin, sample_name, grids, freezing_date)
              VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (e["user_name"], e["pi_name"], e["email"],
             e["origin"], e["sample_name"], e["grids"], e["freezing_date"]),
        )
        cur.execute(
            "UPDATE freezing_bookings SET status='completed' WHERE id=?", [e["id"]]
        )
        send_email(
            e["email"],
            "Cryo-EM Freezing Completed",
            (
                f"Dear {e['user_name']},\n\n"
                f"Your freezing on {e['freezing_date']} is completed.\n\n"
                f"Cryo-EM Team"
            ),
        )

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
