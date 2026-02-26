import os
import datetime
import MySQLdb
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mysqldb import MySQL

app = Flask(__name__)
app.secret_key = 'cryo_em_secret_key_mysql'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=30)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
mail = Mail(app)

MYSQL_HOST = "localhost"
MYSQL_USER = "root"       
MYSQL_PASSWORD = ""       
MYSQL_DBNAME = "cryo_em_db"

# --- Step 1: Ensure Database Exists ---
try:
    conn = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DBNAME}")
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Database '{MYSQL_DBNAME}' is ready")
except Exception as e:
    print("❌ Error creating database:", e)

# --- Step 2: Configure Flask-MySQL ---
app.config['MYSQL_HOST'] = MYSQL_HOST
app.config['MYSQL_USER'] = MYSQL_USER
app.config['MYSQL_PASSWORD'] = MYSQL_PASSWORD
app.config['MYSQL_DB'] = MYSQL_DBNAME
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
mysql = MySQL(app)

# --- Step 3: Auto-create Tables ---
def init_db():
    cur = mysql.connection.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100),
        email VARCHAR(150) UNIQUE,
        password_hash VARCHAR(255),
        role ENUM('user','admin') DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ✅ Imaging Bookings (added origin + esm)
    cur.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_name VARCHAR(100),
        pi_name VARCHAR(100),
        email VARCHAR(150),
        origin VARCHAR(100),
        esm VARCHAR(150),
        sample_name VARCHAR(150),
        reg_type ENUM('imaging','screening') DEFAULT 'imaging',
        grids INT CHECK (grids <= 4),
        days INT CHECK (days <= 4),
        status ENUM('waiting','ongoing','completed') DEFAULT 'waiting',
        registration_date DATE,
        completion_date DATE,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # remove unique index on email if it exists (from previous versions)
    try:
        cur.execute("ALTER TABLE bookings DROP INDEX email")
    except Exception:
        # index might be named differently or not exist; ignore errors
        pass
    # ensure reg_type column in any older installs
    try:
        cur.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reg_type ENUM('imaging','screening') DEFAULT 'imaging'")
    except Exception:
        pass

    # ✅ Freezing Bookings
    cur.execute("""CREATE TABLE IF NOT EXISTS freezing_bookings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_name VARCHAR(100),
        pi_name VARCHAR(100),
        email VARCHAR(150) UNIQUE,
        origin VARCHAR(100),
        sample_name VARCHAR(150),
        grids INT CHECK (grids <= 8),
        freezing_date DATE,
        status ENUM('active','completed') DEFAULT 'active',
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ✅ Completed Freezing
    cur.execute("""CREATE TABLE IF NOT EXISTS completed_freezing (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_name VARCHAR(100),
        pi_name VARCHAR(100),
        email VARCHAR(150),
        origin VARCHAR(100),
        sample_name VARCHAR(150),
        grids INT,
        freezing_date DATE,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    mysql.connection.commit()
    cur.close()

with app.app_context():
    init_db()

# --- Helper Functions ---
def get_slideshow_images():
    try:
        slideshow_dir = os.path.join(app.static_folder, 'slideshow')
        if not os.path.exists(slideshow_dir):
            return []
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif')
        return [f for f in os.listdir(slideshow_dir) if f.lower().endswith(valid_extensions)]
    except Exception as e:
        print(f"Error getting slideshow images: {e}")
        return []

def send_email(recipient, subject, body):
    try:
        msg = Message(subject, recipients=[recipient])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# --- Main Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    slideshow_images = get_slideshow_images()
    return render_template('home.html', slideshow_images=slideshow_images)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/team')
def team():
    return render_template('team.html')

@app.route('/facility')
def facility():
    return render_template('facility.html')

@app.route('/equipments')
def equipments():
    return render_template('equipments.html')

@app.route('/publication')
def publications():
    return render_template('pub.html')

# --- Slot Register Route ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        reg_type = request.form['reg_type']
        user_name = request.form['user_name']
        pi_name = request.form['pi_name']
        email = request.form['email']
        origin = request.form.get('origin', '')
        esm = request.form.get('esm', '')
        sample_name = request.form['sample_name']

        cur = mysql.connection.cursor()

        # -------- IMAGING SLOT --------
        if reg_type == "imaging":
            grids = int(request.form.get('grids') or 0)
            days = int(request.form.get('days') or 0)

            # allow same email for different types, only prevent multiple imaging/waiting or ongoing
            cur.execute("SELECT * FROM bookings WHERE email=%s AND status IN ('waiting','ongoing') AND reg_type='imaging'", [email])
            if cur.fetchone():
                flash("This email is already registered for an Imaging slot.")
                return redirect(url_for('register'))

            cur.execute("""INSERT INTO bookings 
                (user_name, pi_name, email, origin, esm, sample_name, reg_type, grids, days, registration_date, status) 
                VALUES (%s,%s,%s,%s,%s,%s,'imaging',%s,%s,%s,'waiting')""",
                (user_name, pi_name, email, origin, esm, sample_name, grids, days, datetime.date.today()))
            mysql.connection.commit()

            send_email(email, "Cryo-EM Imaging Slot Registered",
                       f"Dear {user_name},\n\nYour Imaging slot has been registered.\nPI: {pi_name}\nSample: {sample_name}\nGrids: {grids}\nDays: {days}\n\nCryo-EM Team")
            return redirect(url_for('list_view'))

        # -------- FREEZING SLOT --------
        elif reg_type == "freezing":
            grids = int(request.form.get('grids_freezing') or 0)  # ✅ FIXED
            freezing_date = request.form.get('freezing_date')

            cur.execute("SELECT * FROM freezing_bookings WHERE email=%s AND status='active'", [email])
            if cur.fetchone():
                flash("This email is already registered in Freezing Schedule.")
                return redirect(url_for('register'))

            cur.execute("SELECT COALESCE(SUM(grids),0) as total FROM freezing_bookings WHERE freezing_date=%s AND status='active'", [freezing_date])
            total = cur.fetchone()['total']
            if total + grids > 8:
                flash(f"Grid limit exceeded. Only {8 - total} grids left for this date.")
                return redirect(url_for('register'))

            cur.execute("""INSERT INTO freezing_bookings 
                (user_name, pi_name, email, origin, sample_name, grids, freezing_date, status, registered_at) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,'active',NOW())""",
                (user_name, pi_name, email, origin, sample_name, grids, freezing_date))
            mysql.connection.commit()

            send_email(email, "Cryo-EM Freezing Slot Registered",
                       f"Dear {user_name},\n\nYour Freezing slot has been registered.\nPI: {pi_name}\nSample: {sample_name}\nGrids: {grids}\nDate: {freezing_date}\n\nCryo-EM Team")
            return redirect(url_for('freezing_schedule'))
        # -------- SCREENING SLOT --------
        elif reg_type == "screening":
            grids = int(request.form.get('grids_screening') or 0)

            # prevent two screening slots
            cur.execute("SELECT * FROM bookings WHERE email=%s AND status IN ('waiting','ongoing') AND reg_type='screening'", [email])
            if cur.fetchone():
                flash("This email is already registered for a Screening slot.")
                return redirect(url_for('register'))

            # store as a normal booking with days=0 and reg_type flag
            cur.execute("""INSERT INTO bookings 
                (user_name, pi_name, email, origin, esm, sample_name, reg_type, grids, days, registration_date, status) 
                VALUES (%s,%s,%s,%s,%s,%s,'screening',%s,0,%s,'waiting')""",
                (user_name, pi_name, email, origin, esm, sample_name, grids, datetime.date.today()))
            mysql.connection.commit()

            send_email(email, "Cryo-EM Screening Slot Registered",
                       f"Dear {user_name},\n\nYour Screening slot has been registered.\nPI: {pi_name}\nSample: {sample_name}\nGrids: {grids}\n\nCryo-EM Team")
            return redirect(url_for('list_view'))

        cur.close()

    return render_template('register.html')

# --- List (Imaging Slots) ---
@app.route('/list')
def list_view():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.execute("SELECT * FROM bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.close()
    return render_template('list.html', ongoing_slots=ongoing, waiting_slots=waiting)

# --- Freezing Schedule ---
@app.route('/freezing_schedule')
def freezing_schedule():
    cur = mysql.connection.cursor()
    today = datetime.date.today()

    cur.execute("SELECT * FROM freezing_bookings WHERE freezing_date < %s AND status='active'", [today])
    expired = cur.fetchall()
    for e in expired:
        cur.execute("""INSERT INTO completed_freezing 
            (user_name, pi_name, email, origin, sample_name, grids, freezing_date) 
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (e['user_name'], e['pi_name'], e['email'], e['origin'], e['sample_name'], e['grids'], e['freezing_date']))
        cur.execute("UPDATE freezing_bookings SET status='completed' WHERE id=%s", [e['id']])
        send_email(e['email'], "Cryo-EM Freezing Completed",
                   f"Dear {e['user_name']},\n\nYour freezing on {e['freezing_date']} is completed.\n\nCryo-EM Team")

    mysql.connection.commit()

    cur.execute("SELECT * FROM freezing_bookings WHERE status='active'")
    active = cur.fetchall()
    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed = cur.fetchall()
    cur.close()
    return render_template('freezingschedule.html', active_slots=active, completed_slots=completed)

# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", [username])
        admin_user = cur.fetchone()
        cur.close()

        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session.permanent = True
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))

        flash('Invalid username or password')
    return render_template('admin.html')

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM bookings WHERE status='waiting'")
    waiting_regs = cur.fetchall()
    cur.execute("SELECT * FROM bookings WHERE status='ongoing'")
    ongoing_regs = cur.fetchall()
    cur.close()
    return render_template('admin_panel.html',
                           waiting_registrations=waiting_regs,
                           ongoing_registrations=ongoing_regs)

@app.route('/admin/load/<int:booking_id>')
def load_registration(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    cur = mysql.connection.cursor()
    cur.execute("UPDATE bookings SET status='ongoing' WHERE id=%s", [booking_id])
    cur.execute("SELECT * FROM bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    mysql.connection.commit()
    cur.close()

    if reg:
        send_email(reg['email'], "Cryo-EM Slot Loaded",
                   f"Dear {reg['user_name']},\n\nYour grids are loaded today.\n\nCryo-EM Team")

    return redirect(url_for('admin_panel'))

@app.route('/admin/complete/<int:booking_id>')
def complete_registration(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    cur = mysql.connection.cursor()
    cur.execute("UPDATE bookings SET status='completed', completion_date=%s WHERE id=%s",
                (datetime.date.today(), booking_id))
    cur.execute("SELECT * FROM bookings WHERE id=%s", [booking_id])
    reg = cur.fetchone()
    mysql.connection.commit()
    cur.close()

    if reg:
        send_email(reg['email'], "Cryo-EM Slot Completed",
                   f"Dear {reg['user_name']},\n\nYour slot is completed. Kindly collect your data.\n\nCryo-EM Team")

    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<int:booking_id>')
def delete_registration(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM bookings WHERE id=%s", [booking_id])
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin/history', endpoint='admin_history')
def history():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    cur = mysql.connection.cursor()

    # Fetch completed imaging slots
    cur.execute("SELECT * FROM bookings WHERE status='completed' ORDER BY completion_date DESC")
    completed_imaging = cur.fetchall()

    # Fetch completed freezing slots
    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed_freezing = cur.fetchall()

    cur.close()

    return render_template('history.html',
                           completed_imaging=completed_imaging,
                           completed_freezing=completed_freezing)


@app.before_request
def check_admin_session():
    if 'admin_logged_in' in session and request.endpoint:
        allowed = [
            'admin_panel', 'admin_logout', 'load_registration','admin_history',
            'complete_registration', 'delete_registration', 'static'
        ]
        if request.endpoint not in allowed:
            session.pop('admin_logged_in', None)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
