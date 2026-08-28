import os
from flask import Blueprint, render_template, current_app, redirect, url_for

public_bp = Blueprint("public", __name__)


def get_slideshow_images():
    """Return list of image filenames from static/slideshow/."""
    try:
        slideshow_dir = os.path.join(current_app.static_folder, "slideshow")
        if not os.path.exists(slideshow_dir):
            return []
        valid = (".jpg", ".jpeg", ".png", ".gif")
        return [f for f in os.listdir(slideshow_dir) if f.lower().endswith(valid)]
    except Exception as exc:
        current_app.logger.error(f"Slideshow error: {exc}")
        return []


@public_bp.route("/")
def index():
    return redirect(url_for("public.home"))


@public_bp.route("/home")
def home():
    slideshow_images = get_slideshow_images()
    return render_template("home.html", slideshow_images=slideshow_images)


@public_bp.route("/about")
def about():
    return render_template("about.html")


@public_bp.route("/team")
def team():
    return render_template("team.html")


@public_bp.route("/facility")
def facility():
    return render_template("facility.html")


@public_bp.route("/workflow")
def workflow():
    return render_template("workflow.html")


@public_bp.route("/equipments")
def equipments():
    return render_template("equipments.html")


@public_bp.route("/publication")
def publications():
    return render_template("pub.html")


@public_bp.route("/events")
def events():
    return render_template("events.html")


@public_bp.route("/community-gallery")
def community_gallery():
    return render_template("community_gallery.html")
