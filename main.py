import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mysqldb import MySQL

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cryo_em_secret_key_mysql')
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=30)

# --- Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
mail = Mail(app)

# --- Database Configuration ---
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'cryo_em_db')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# --- Database Initialization ---
def init_db():
    """Initializes the database tables. Called on first request or manually."""
    try:
        # Check if connection is available
        if mysql.connection is None:
            print("⚠️ MySQL connection not yet available. Tables will be created on first access.")
            return False
            
        cur = mysql.connection.cursor()
        
        # Create Tables
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(150) UNIQUE,
            password_hash VARCHAR(255),
            role ENUM('user','admin') DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

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

        # Maintenance tasks
        try:
            cur.execute("ALTER TABLE bookings DROP INDEX email")
        except: pass
        
        try:
            cur.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reg_type ENUM('imaging','screening') DEFAULT 'imaging'")
        except: pass

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
        print("✅ Database tables verified/created successfully.")
        return True
    except Exception as e:
        print(f"❌ Database init error: {e}")
        return False

# Flag to ensure init_db only runs once successfully
db_initialized = False

@app.before_request
def ensure_db():
    global db_initialized
    if not db_initialized:
        if init_db():
            db_initialized = True

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
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return False
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

        if reg_type == "imaging":
            grids = int(request.form.get('grids') or 0)
            days = int(request.form.get('days') or 0)
            cur.execute("SELECT * FROM bookings WHERE email=%s AND status IN ('waiting','ongoing') AND reg_type='imaging'", [email])
            if cur.fetchone():
                flash("This email is already registered for an Imaging slot.")
                return redirect(url_for('register'))
            cur.execute("""INSERT INTO bookings 
                (user_name, pi_name, email, origin, esm, sample_name, reg_type, grids, days, registration_date, status) 
                VALUES (%s,%s,%s,%s,%s,%s,'imaging',%s,%s,%s,'waiting')""",
                (user_name, pi_name, email, origin, esm, sample_name, grids, days, datetime.date.today()))
            mysql.connection.commit()
            send_email(email, "Cryo-EM Imaging Slot Registered", f"Dear {user_name},\n\nYour Imaging slot has been registered.")
            return redirect(url_for('list_view'))

        elif reg_type == "freezing":
            grids = int(request.form.get('grids_freezing') or 0)
            freezing_date = request.form.get('freezing_date')
            cur.execute("SELECT * FROM freezing_bookings WHERE email=%s AND status='active'", [email])
            if cur.fetchone():
                flash("This email is already registered in Freezing Schedule.")
                return redirect(url_for('register'))
            cur.execute("SELECT COALESCE(SUM(grids),0) as total FROM freezing_bookings WHERE freezing_date=%s AND status='active'", [freezing_date])
            total = cur.fetchone()['total']
            if total + grids > 8:
                flash(f"Grid limit exceeded. Only {8 - total} grids left.")
                return redirect(url_for('register'))
            cur.execute("""INSERT INTO freezing_bookings 
                (user_name, pi_name, email, origin, sample_name, grids, freezing_date, status, registered_at) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,'active',NOW())""",
                (user_name, pi_name, email, origin, sample_name, grids, freezing_date))
            mysql.connection.commit()
            send_email(email, "Cryo-EM Freezing Slot Registered", f"Dear {user_name},\n\nYour Freezing slot has been registered.")
            return redirect(url_for('freezing_schedule'))

        elif reg_type == "screening":
            grids = int(request.form.get('grids_screening') or 0)
            cur.execute("SELECT * FROM bookings WHERE email=%s AND status IN ('waiting','ongoing') AND reg_type='screening'", [email])
            if cur.fetchone():
                flash("This email is already registered for a Screening slot.")
                return redirect(url_for('register'))
            cur.execute("""INSERT INTO bookings 
                (user_name, pi_name, email, origin, esm, sample_name, reg_type, grids, days, registration_date, status) 
                VALUES (%s,%s,%s,%s,%s,%s,'screening',%s,0,%s,'waiting')""",
                (user_name, pi_name, email, origin, esm, sample_name, grids, datetime.date.today()))
            mysql.connection.commit()
            send_email(email, "Cryo-EM Screening Slot Registered", f"Dear {user_name},\n\nYour Screening slot has been registered.")
            return redirect(url_for('list_view'))
        cur.close()
    return render_template('register.html')

@app.route('/list')
def list_view():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM bookings WHERE status='ongoing'")
    ongoing = cur.fetchall()
    cur.execute("SELECT * FROM bookings WHERE status='waiting'")
    waiting = cur.fetchall()
    cur.close()
    return render_template('list.html', ongoing_slots=ongoing, waiting_slots=waiting)

@app.route('/freezing_schedule')
def freezing_schedule():
    cur = mysql.connection.cursor()
    today = datetime.date.today()
    cur.execute("SELECT * FROM freezing_bookings WHERE freezing_date < %s AND status='active'", [today])
    expired = cur.fetchall()
    for e in expired:
        cur.execute("""INSERT INTO completed_freezing (user_name, pi_name, email, origin, sample_name, grids, freezing_date) 
            VALUES (%s,%s,%s,%s,%s,%s,%s)""", (e['user_name'], e['pi_name'], e['email'], e['origin'], e['sample_name'], e['grids'], e['freezing_date']))
    mysql.connection.commit()
    cur.execute("SELECT * FROM freezing_bookings WHERE status='active'")
    active = cur.fetchall()
    cur.execute("SELECT * FROM completed_freezing ORDER BY completed_at DESC")
    completed = cur.fetchall()
    cur.close()
    return render_template('freezingschedule.html', active_slots=active, completed_slots=completed)

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
    return render_template('admin_panel.html', waiting_registrations=waiting_regs, ongoing_registrations=ongoing_regs)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # On local run, try to init immediately
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
