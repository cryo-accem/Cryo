from flask import Blueprint, render_template, request, redirect, url_for, flash
from blueprints.imaging import register_imaging
from blueprints.freezing import register_freezing
from blueprints.screening import register_screening

register_bp = Blueprint("register", __name__)


@register_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        reg_type    = request.form["reg_type"]
        user_name   = request.form["user_name"]
        pi_name     = request.form["pi_name"]
        email       = request.form["email"]
        origin      = request.form.get("origin", "")
        sample_name = request.form["sample_name"]

        # ── Data Collecting (was Imaging) ────────────────────────────────────
        if reg_type == "datacollecting":
            esm   = request.form.get("esm", "")
            grids = int(request.form.get("grids") or 0)
            days  = int(request.form.get("days") or 0)

            success, message = register_imaging(
                user_name, pi_name, email, origin, esm, sample_name, grids, days
            )
            if not success:
                flash(message)
                return redirect(url_for("register.register"))
            return redirect(url_for("imaging.list_view"))

        # ── Screening ────────────────────────────────────────────────────────
        elif reg_type == "screening":
            esm   = request.form.get("esm", "")
            grids = int(request.form.get("grids") or 0)
            days  = int(request.form.get("days") or 0)

            success, message = register_screening(
                user_name, pi_name, email, origin, esm, sample_name, grids, days
            )
            if not success:
                flash(message)
                return redirect(url_for("register.register"))
            return redirect(url_for("screening.screening_list"))

        # ── Freezing ─────────────────────────────────────────────────────────
        elif reg_type == "freezing":
            grids         = int(request.form.get("grids_freezing") or 0)
            freezing_date = request.form.get("freezing_date")

            success, message = register_freezing(
                user_name, pi_name, email, origin, sample_name, grids, freezing_date
            )
            if not success:
                flash(message)
                return redirect(url_for("register.register"))
            return redirect(url_for("freezing.freezing_schedule"))

    return render_template("register.html")
