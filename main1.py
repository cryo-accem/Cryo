import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId

# --- App Initialization and Configuration ---
app = Flask(__name__)
app.secret_key = 'cryo_em_secret_key_mongodb'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=30)

# --- Email Configuration ---
# For production, set these as environment variables
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
mail = Mail(app)

# --- MongoDB Connection Setup ---
# For production, set this as an environment variable
MONGO_URI = os.environ.get('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client.cryo_em_db

# Define collections
registrations_collection = db.registrations
history_collection = db.history
users_collection = db.users

# additional collections needed for freezing workflow
freezing_bookings_collection = db.freezing_bookings
completed_freezing_collection = db.completed_freezing

# ensure useful indexes
registrations_collection.create_index([('email', 1), ('status', 1), ('reg_type', 1)])
# only one active freezing booking per email
freezing_bookings_collection.create_index('email', unique=True, partialFilterExpression={'status': 'active'})

# --- Helper Functions ---
def get_slideshow_images():
    """Gets a list of image filenames from the static/slideshow directory."""
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
    """Sends an email using Flask-Mail."""
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

# --- NEW ROUTE ---
@app.route('/equipments')
def equipments():
    return render_template('equipments.html')

@app.route('/publication')
def publications():
    return render_template('pub.html')

# --- Data-Driven Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        reg_type = request.form.get('reg_type')
        user_name = request.form['user_name']
        pi_name = request.form['pi_name']
        email = request.form['email']
        origin = request.form.get('origin', '')
        esm = request.form.get('esm', '')
        sample_name = request.form['sample_name']

        # ---------- IMAGING ----------
        if reg_type == 'imaging':
            grids = int(request.form.get('grids') or 0)
            days = int(request.form.get('days') or 0)

            existing = registrations_collection.find_one({
                'email': email,
                'status': {'$in': ['waiting', 'ongoing']},
                'reg_type': 'imaging'
            })
            if existing:
                flash('This email is already registered for an Imaging slot.')
                return redirect(url_for('register'))

            doc = {
                'reg_type': 'imaging',
                'user_name': user_name,
                'pi_name': pi_name,
                'email': email,
                'origin': origin,
                'esm': esm,
                'sample_name': sample_name,
                'grids': grids,
                'days': days,
                'registration_date': datetime.datetime.now().strftime('%Y-%m-%d'),
                'status': 'waiting'
            }
            registrations_collection.insert_one(doc)

            position = registrations_collection.count_documents({'status': 'waiting', 'reg_type': 'imaging'})
            subject = 'Cryo-EM Imaging Slot Registered'
            body = f"""
Dear {user_name},

Your Imaging slot has been registered.
PI: {pi_name}
Sample: {sample_name}
Grids: {grids}
Days: {days}

Cryo-EM Team"""
            send_email(email, subject, body)
            return redirect(url_for('list_view'))

        # ---------- FREEZING ----------
        elif reg_type == 'freezing':
            grids = int(request.form.get('grids_freezing') or 0)
            freezing_date = request.form.get('freezing_date')

            existing = freezing_bookings_collection.find_one({
                'email': email,
                'status': 'active'
            })
            if existing:
                flash('This email is already registered in Freezing Schedule.')
                return redirect(url_for('register'))

            total = freezing_bookings_collection.aggregate([
                {'$match': {'freezing_date': freezing_date, 'status': 'active'}},
                {'$group': {'_id': None, 'total': {'$sum': '$grids'}}}
            ])
            total_grids = 0
            for r in total:
                total_grids = r.get('total', 0)
            if total_grids + grids > 8:
                flash(f"Grid limit exceeded. Only {8 - total_grids} grids left for this date.")
                return redirect(url_for('register'))

            freezing_bookings_collection.insert_one({
                'user_name': user_name,
                'pi_name': pi_name,
                'email': email,
                'origin': origin,
                'sample_name': sample_name,
                'grids': grids,
                'freezing_date': freezing_date,
                'status': 'active',
                'registered_at': datetime.datetime.now()
            })

            send_email(email, 'Cryo-EM Freezing Slot Registered',
                       f"Dear {user_name},\n\nYour Freezing slot has been registered.\nPI: {pi_name}\nSample: {sample_name}\nGrids: {grids}\nDate: {freezing_date}\n\nCryo-EM Team")
            return redirect(url_for('freezing_schedule'))

        # ---------- SCREENING ----------
        elif reg_type == 'screening':
            grids = int(request.form.get('grids_screening') or 0)

            existing = registrations_collection.find_one({
                'email': email,
                'status': {'$in': ['waiting', 'ongoing']},
                'reg_type': 'screening'
            })
            if existing:
                flash('This email is already registered for a Screening slot.')
                return redirect(url_for('register'))

            doc = {
                'reg_type': 'screening',
                'user_name': user_name,
                'pi_name': pi_name,
                'email': email,
                'origin': origin,
                'esm': esm,
                'sample_name': sample_name,
                'grids': grids,
                'days': 0,
                'registration_date': datetime.datetime.now().strftime('%Y-%m-%d'),
                'status': 'waiting'
            }
            registrations_collection.insert_one(doc)

            send_email(email, 'Cryo-EM Screening Slot Registered',
                       f"Dear {user_name},\n\nYour Screening slot has been registered.\nPI: {pi_name}\nSample: {sample_name}\nGrids: {grids}\n\nCryo-EM Team")
            return redirect(url_for('list_view'))

    return render_template('register.html')

@app.route('/list')
def list_view():
    ongoing_slots = list(registrations_collection.find({'status': 'ongoing'}))
    waiting_slots = list(registrations_collection.find({'status': 'waiting'}))
    return render_template('list.html', ongoing_slots=ongoing_slots, waiting_slots=waiting_slots)

@app.route('/freezing_schedule')
def freezing_schedule():
    today = datetime.date.today()

    # move expired to completed_freezing
    expired = list(freezing_bookings_collection.find({'freezing_date': {'$lt': today}, 'status': 'active'}))
    for e in expired:
        entry = e.copy()
        entry.pop('_id', None)
        entry['completed_at'] = datetime.datetime.now()
        completed_freezing_collection.insert_one(entry)
        freezing_bookings_collection.update_one({'_id': e['_id']}, {'$set': {'status': 'completed'}})
        send_email(e['email'], 'Cryo-EM Freezing Completed',
                   f"Dear {e['user_name']},\n\nYour freezing on {e['freezing_date']} is completed.\n\nCryo-EM Team")

    active = list(freezing_bookings_collection.find({'status': 'active'}))
    completed = list(completed_freezing_collection.find({}).sort('completed_at', -1))
    return render_template('freezingschedule.html', active_slots=active, completed_slots=completed)

@app.route('/history')
def history():
    history_entries = list(history_collection.find({}))
    completed_freeze = list(completed_freezing_collection.find({}))
    return render_template('history.html', history_entries=history_entries, completed_freezing=completed_freeze)

# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']
        
        admin_user = users_collection.find_one({'username': username})
        
        if admin_user and check_password_hash(admin_user['password'], password):
            # --- UPDATED SESSION LOGIC ---
            session.permanent = True
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        
        flash('Invalid username or password')
    return render_template('admin.html')

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    waiting_regs = list(registrations_collection.find({'status': 'waiting'}))
    ongoing_regs = list(registrations_collection.find({'status': 'ongoing'}))
    
    return render_template('admin_panel.html',
                           waiting_registrations=waiting_regs,
                           ongoing_registrations=ongoing_regs)

@app.route('/admin/load/<string:doc_id>')
def load_registration(doc_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    registrations_collection.update_one(
        {'_id': ObjectId(doc_id)},
        {'$set': {'status': 'ongoing'}}
    )

    registration = registrations_collection.find_one({'_id': ObjectId(doc_id)})
    if registration:
        subject = "Cryo-EM Slot Loaded"
        body = """
Dear {user_name},

Your grids are loaded today and ready for imaging.
Kindly contact the EM Manager for your slot date.

Thanks & Regards,
Cryo-EM Team,
IISc, Bangalore.
""".format(user_name=registration['user_name'])
        send_email(registration['email'], subject, body)
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/complete/<string:doc_id>')
def complete_registration(doc_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    registration = registrations_collection.find_one_and_delete({'_id': ObjectId(doc_id)})
    
    if registration:
        registration['completion_date'] = datetime.datetime.now().strftime('%Y-%m-%d')
        history_collection.insert_one(registration)

        subject = "Cryo-EM Slot Completed"
        body = """
Dear {user_name},

Your slot has been completed.
Kindly collect your data at the earliest.
Your slot and the consumable charges are ____

Thank you for your support and cooperation.

Thanks & Regards,
Cryo-EM Team,
IISc Bangalore.
""".format(user_name=registration['user_name'])
        send_email(registration['email'], subject, body)
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<string:doc_id>')
def delete_registration(doc_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    registration = registrations_collection.find_one_and_delete({'_id': ObjectId(doc_id)})
    
    if registration:
        subject = "Cryo-EM Slot Registration Deleted"
        body = f"Dear {registration['user_name']},\n\nYour registration has been deleted by the admin."
        send_email(registration['email'], subject, body)
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin/history', endpoint='admin_history')
def admin_history():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    completed_imaging = list(registrations_collection.find({'status': 'completed'}).sort('completion_date', -1))
    completed_freezing = list(completed_freezing_collection.find({}).sort('completed_at', -1))
    return render_template('history.html',
                           completed_imaging=completed_imaging,
                           completed_freezing=completed_freezing)

@app.before_request
def check_admin_session():
    """Logs out admin if they navigate away from admin pages."""
    if 'admin_logged_in' in session and request.endpoint:
        allowed_endpoints = [
            'admin_panel', 'admin_logout', 'load_registration',
            'complete_registration', 'delete_registration', 'admin_history', 'static'
        ]
        if request.endpoint not in allowed_endpoints:
            session.pop('admin_logged_in', None)

if __name__ == '__main__':
    # For local development
    app.run(debug=True, host='0.0.0.0', port=5000)