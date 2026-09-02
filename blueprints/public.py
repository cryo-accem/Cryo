import os
import csv
import io
import json
import time
import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from flask import Blueprint, render_template, current_app, redirect, url_for, Response, jsonify
from database import get_db

public_bp = Blueprint("public", __name__)
_publication_cache = {"timestamp": 0.0, "count": 36, "source": "curated fallback"}
_structure_cache = {"timestamp": 0.0, "count": 69, "source": "facility logs"}
_structure_breakdown_cache = {"timestamp": 0.0, "data": {}}
EMDB_PIS = (
    ("Somnath Dutta", "Dutta"),
    ("Siddhartha P. Sarma", "Sarma"),
    ("Raghavan Varadarajan", "Varadarajan"),
    ("Vinothkumar Kutti Ragunath", "Vinothkumar"),
    ("Vidya Mangala Prasad", "Prasad"),
    ("N. Ravishankar", "Ravishankar"),
    ("Aravind Penmatsa", "Penmatsa"),
)

PI_USERS = [
    ("Prof. Dipshikha Chakravortty", 1), ("Prof. Dipankar Chatterji", 1), ("Prof. K. Suguna", 1),
    ("Prof. B. Gopal", 1), ("Dr. Aravind Pentamasa", 5), ("Dr. Somnath Dutta", 8),
    ("Dr. Ashok Sekhar", 1), ("Dr. Jayanta Chatterjee", 1), ("Dr. Mahavir Singh", 2),
    ("Dr. Tanweer Hussain", 4), ("Dr. Raghavan Varadarajan", 5), ("Dr. Vidhya Mangala Prasad", 8),
    ("Dr. Amit Baidya", 3), ("Dr. Mahipal Ganji", 2), ("Dr. Saibal Chatterjee", 1),
    ("Dr. Saravanan Palani", 1), ("Dr. Srimonta Gayen", 3), ("Prof. Siddhartha P. Sarma", 2),
    ("Dr. Amit Singh", 2), ("Dr. Deepak K. Saini", 1), ("Dr. Kartik Sunagar", 1),
    ("Prof. P. K. Das", 1), ("Prof. Aninda J. Bhattacharyya", 1), ("Dr. Subinoy Rana", 1),
    ("Dr. Debasis Das", 3), ("Prof. Uday Maitra", 9), ("Prof. Joydeep Basu", 1),
    ("Dr. Sivaprakasam Ramamoorthy", 2),
]

ACADEMIC_USERS = [
    ("NCCS, Pune", 2), ("IIT-Bombay", 3), ("InStem", 1), ("Bose Institute", 4),
    ("Siddaganga Institute of Technology", 2), ("IISER-Mohali", 4), ("IISER-Pune", 1),
    ("NICED-ICMR, Kolkata", 3), ("CDRI, Lucknow", 10), ("Manipal College of Dental Sciences", 1),
    ("AIIMS, Delhi", 2), ("THSTI, New Delhi", 4), ("IICB, Kolkata", 1),
    ("Raman Research Institute", 1), ("IIT-Kanpur", 10), ("IIT-Delhi", 3),
    ("University of Kalyani", 1), ("JSS College of Pharmacy", 2), ("IISER-TVM", 4),
    ("ICAR-IVRI", 3), ("CSIR-NIO", 1),
]

INDUSTRY_USERS = [
    "INTAS Pharmaceuticals Ltd.", "Aragen Life Sciences Pvt. Ltd.", "Biovet Pvt. Ltd.",
    "Venture Incubation Center, Pune", "Aurea Biolabs", "PS Therapy, Coimbatore",
    "DifGen Pharmaceuticals Pvt. Ltd.", "Pidilite Industries Ltd.", "Enzene Biosciences Ltd.",
    "Hindustan Unilever Ltd.", "Bekaert Industries, Pune", "Vastu Vihar Biotech Pvt. Ltd.",
    "Go Green Bioenergy India Pvt. Ltd.", "Cedal Nano, IR", "SPARC, Mumbai",
    "Embright Infotech Pvt. Ltd.", "ITC, Bangalore", "Jodas Expoim Pvt. Ltd.",
    "FTF Pharma Pvt. Ltd.", "Alkem Laboratories Ltd., Mumbai", "Akay Natural Ingredients Pvt. Ltd.",
    "Almora Botanica UK Ltd.", "Zydus Lifesciences", "Adex Pharma Consultancy Services",
    "Global Calcium Pharma", "Expert Vision Labs", "Hitech Formulations Pvt. Ltd.", "Pfizer",
    "Alembic Pharmaceuticals", "Shilpa Medicare", "Pulse Pharma Ltd.",
    "Serum Institute of India (SII)", "Lupin Biotech, Delhi", "Slayback Pharma",
    "Gulfic Bioscience Ltd.", "Micro Labs Ltd., Bangalore", "Natco Pharma Ltd.",
    "Sun Pharmaceutical Industries Ltd.", "Mylan Laboratories", "Aurigene Pharmaceutical Services Ltd.",
    "Botanic Healthcare", "Bharat Serums and Vaccines Ltd.", "Hetero Labs Ltd.", "Cipla India Ltd.",
]


def _user_csv(filename, category, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Category", "PI / Institution / Organisation", "Users"])
    writer.writerows((category, label, count) for label, count in rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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


def get_user_statistics():
    """Combine the published baseline with newly logged registrations."""
    baseline = {"Internal": 72, "External": 54, "Industry": 44}
    try:
        conn = get_db()
        cur = conn.cursor()
        registrations = []
        for table in ("bookings", "screening_bookings", "freezing_bookings"):
            cur.execute(f"SELECT origin FROM {table} WHERE origin IS NOT NULL AND origin != ''")
            registrations.extend(cur.fetchall())
        conn.close()

        for row in registrations:
            origin = row["origin"] if isinstance(row, dict) else row[0]
            normalized = origin.strip().lower()
            category = (
                "Industry" if "industry" in normalized
                else "Internal" if "internal" in normalized
                else "External" if "external" in normalized or "academic" in normalized
                else origin.strip()
            )
            baseline[category] = baseline.get(category, 0) + 1
        return sorted(baseline.items(), key=lambda item: item[1], reverse=True)
    except Exception as exc:
        current_app.logger.error(f"User statistics error: {exc}")
        return []


# Color palette for pie charts (vibrant and visually appealing)
CHART_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#52C9B7",
    "#ED7E4D", "#6C96C2", "#FF8A5B", "#4A9B7F", "#D4A574",
    "#7B68EE", "#FF69B4", "#20B2AA", "#FFB347", "#87CEEB",
    "#FF7F50", "#32CD32", "#FFD700", "#FF4500", "#00CED1",
]


def get_color_for_index(index):
    """Get a color from the palette for a given index."""
    return CHART_COLORS[index % len(CHART_COLORS)]


def get_facility_metrics():
    """Return published research and completed structure-project totals."""
    return {
        "publications": get_publication_count(),
        "structures": "85+",
    }


def get_publication_count():
    """Count unique OpenAlex works matching the facility acknowledgement terms."""
    if time.time() - _publication_cache["timestamp"] < 3600:
        return _publication_cache["count"]

    try:
        works = {}
        for term in ("ACCEM", "cryo-EM IISc"):
            url = "https://api.openalex.org/works?search=" + quote(term) + "&per-page=200"
            request = Request(url, headers={"User-Agent": "ACCEM facility dashboard"})
            with urlopen(request, timeout=15) as response:
                payload = json.load(response)
            for work in payload.get("results", []):
                work_id = work.get("id")
                if work_id:
                    works[work_id] = work

        count = len(works)
        if count:
            _publication_cache.update(
                timestamp=time.time(), count=count, source="OpenAlex"
            )
        return _publication_cache["count"]
    except (OSError, ValueError, KeyError) as exc:
        current_app.logger.warning("OpenAlex publication lookup failed: %s", exc)
        return _publication_cache["count"]


def get_emdb_structure_count():
    """Count unique EMDB entries associated with the facility's PIs."""
    breakdown = get_emdb_structure_breakdown()
    return len({entry_id for entries in breakdown.values() for entry_id in entries})


def get_emdb_structure_breakdown():
    """Return deduplicated EMDB entry IDs grouped by committee PI."""
    if time.time() - _structure_breakdown_cache["timestamp"] < 3600:
        return _structure_breakdown_cache["data"]

    try:
        result = {}
        for display_name, search_term in EMDB_PIS:
            ids = set()
            for page in range(1, 11):
                url = (
                    "https://www.ebi.ac.uk/emdb/api/search/"
                    + quote(search_term)
                    + f"?rows=100&page={page}"
                )
                request = Request(url, headers={"User-Agent": "ACCEM facility dashboard"})
                with urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                page_ids = set()
                for entry in payload:
                    entry_id = entry.get("emdb_id") or entry.get("_id")
                    deposited = entry.get("admin", {}).get("key_dates", {}).get("deposition", "")
                    year_text = deposited[:4]
                    metadata = json.dumps(entry, ensure_ascii=False).lower()
                    has_iisc = "iisc" in metadata or "indian institute of science" in metadata
                    has_facility = any(
                        term in metadata
                        for term in (
                            "accem",
                            "cryo-em",
                            "cryo em",
                            "cryoelectron",
                            "advanced centre for cryo",
                        )
                    )
                    if (
                        entry_id
                        and has_iisc
                        and has_facility
                        and year_text.isdigit()
                        and 2018 <= int(year_text) <= datetime.date.today().year
                    ):
                        page_ids.add(entry_id)
                ids.update(page_ids)
                if len(payload) < 100:
                    break
            result[display_name] = sorted(ids)

        _structure_breakdown_cache.update(timestamp=time.time(), data=result)
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        current_app.logger.warning("EMDB structure lookup failed: %s", exc)
        return _structure_breakdown_cache["data"]

@public_bp.route("/")
def index():
    return redirect(url_for("public.home"))


@public_bp.route("/home")
def home():
    slideshow_images = get_slideshow_images()
    return render_template("home.html", slideshow_images=slideshow_images)


@public_bp.route("/api/user-statistics")
def api_user_statistics():
    """API endpoint to fetch user statistics as JSON for dynamic chart updates."""
    try:
        stats = get_user_statistics()
        
        # Calculate percentages and prepare chart data
        total_users = sum(count for _, count in stats)
        chart_data = []
        
        if total_users > 0:
            running_percentage = 0
            for index, (label, count) in enumerate(stats):
                percentage = (count / total_users) * 100
                chart_data.append({
                    'label': label,
                    'value': count,
                    'percentage': round(percentage, 1),
                    'color': get_color_for_index(index),
                    'start': round(running_percentage, 1),
                    'end': round(running_percentage + percentage, 1)
                })
                running_percentage += percentage
        
        return jsonify({
            'success': True,
            'total': total_users,
            'data': chart_data,
            'metrics': get_facility_metrics(),
        })
    except Exception as exc:
        current_app.logger.error(f"API error: {exc}")
        return jsonify({'success': False, 'error': str(exc)}), 500


@public_bp.route("/downloads/iisc-users.csv")
def download_iisc_users():
    return _user_csv("iisc-users.csv", "IISc internal", PI_USERS)


@public_bp.route("/downloads/academic-users.csv")
def download_academic_users():
    return _user_csv("academic-external-users.csv", "Academic / external", ACADEMIC_USERS)


@public_bp.route("/downloads/industry-users.csv")
def download_industry_users():
    return _user_csv(
        "industry-users.csv",
        "Industry",
        [(organisation, 1) for organisation in INDUSTRY_USERS],
    )


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
