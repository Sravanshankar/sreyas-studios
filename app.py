import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'sreyas_studios_super_secret_key'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database helper
DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()
    return cur

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Context processor to inject user status and info into all templates
@app.context_processor
def inject_user_info():
    is_logged_in = 'user_id' in session
    is_admin = session.get('is_admin', False)
    user_name = session.get('user_name', '')
    user_image = session.get('user_image', '')
    return dict(
        is_logged_in=is_logged_in,
        is_admin=is_admin,
        user_name=user_name,
        user_image=user_image
    )

# --- Routes ---

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# About page
@app.route('/about')
def about():
    return render_template('about.html')

# Contact page
@app.route('/contact')
def contact():
    return render_template('contact.html')

# Testimonial page
@app.route('/testimonial')
def testimonial():
    # Fetch some rated bookings for reviews
    reviews = query_db('''
        SELECT s.rating, s.review, u.name as user_name, ser.name as service_name, s.date
        FROM slots s
        JOIN users u ON s.booked_by = u.id
        JOIN services ser ON s.service_id = ser.id
        WHERE s.rating IS NOT NULL
        ORDER BY s.id DESC LIMIT 5
    ''')
    return render_template('testimonial.html', reviews=reviews)

# Services page (displays services and available slots)
@app.route('/services')
def services():
    services_list = query_db('SELECT * FROM services')
    
    # Fetch available (unbooked) slots grouped by service
    available_slots = query_db('''
        SELECT s.*, ser.name as service_name 
        FROM slots s
        JOIN services ser ON s.service_id = ser.id
        WHERE s.is_booked = 0 AND s.status = 'Upcoming'
        ORDER BY s.date ASC, s.time ASC
    ''')
    
    # Organize slots by service_id
    slots_by_service = {}
    for slot in available_slots:
        s_id = slot['service_id']
        if s_id not in slots_by_service:
            slots_by_service[s_id] = []
        slots_by_service[s_id].append(slot)
        
    return render_template('services.html', services=services_list, slots_by_service=slots_by_service)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 1. Admin login check
        if email == 'Sreya@gmail.com' and password == 'sreya@123':
            session['user_id'] = 'admin'
            session['user_name'] = "Sreya (Admin)"
            session['is_admin'] = True
            session['user_image'] = 'admin.png' # Fallback placeholder
            flash('Welcome back, Admin Sreya!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        # 2. Regular user login check
        user = query_db('SELECT * FROM users WHERE email = ?', [email], one=True)
        if user and user['password'] == password: # Simple plaintext comparison as requested/simplified
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = False
            session['user_image'] = user['image_path'] or 'default-user.jpg'
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'danger')
            
    return render_template('login.html')

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        location = request.form.get('location')
        password = request.form.get('password')
        
        # Validate fields
        if not name or not phone or not email or not location or not password:
            flash('All fields are required!', 'danger')
            return render_template('register.html')
            
        # Check if user exists
        existing_user = query_db('SELECT * FROM users WHERE email = ?', [email], one=True)
        if existing_user:
            flash('Email already registered!', 'danger')
            return render_template('register.html')
            
        # Handle file upload
        file = request.files.get('image')
        filename = 'default-user.jpg'
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Ensure unique filename to prevent overwriting
                base, ext = os.path.splitext(filename)
                count = 1
                while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
                    filename = f"{base}_{count}{ext}"
                    count += 1
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            else:
                flash('Invalid file extension. Allowed images: png, jpg, jpeg, gif', 'danger')
                return render_template('register.html')
                
        # Insert user
        try:
            execute_db(
                'INSERT INTO users (name, phone, email, location, image_path, password) VALUES (?, ?, ?, ?, ?, ?)',
                [name, phone, email, location, filename, password]
            )
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('An error occurred during registration.', 'danger')
            
    return render_template('register.html')

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

# Book service flow (Payment selection and Slot configuration)
@app.route('/book/<int:service_id>', methods=['GET', 'POST'])
def book_service_flow(service_id):
    if 'user_id' not in session or session.get('is_admin'):
        flash('Please login as a user to book an appointment.', 'warning')
        return redirect(url_for('login'))
        
    service = query_db('SELECT * FROM services WHERE id = ?', [service_id], one=True)
    if not service:
        flash('Service not found.', 'danger')
        return redirect(url_for('services'))
        
    if request.method == 'POST':
        slot_id = request.form.get('slot_id')
        payment_method = request.form.get('payment_method')
        payment_status = request.form.get('payment_status', 'Pending')
        
        if not slot_id or not payment_method:
            flash('Please select both a payment method and an available slot.', 'danger')
            return redirect(url_for('book_service_flow', service_id=service_id))
            
        slot = query_db('SELECT * FROM slots WHERE id = ? AND is_booked = 0', [slot_id], one=True)
        if not slot:
            flash('Selected slot is no longer available.', 'danger')
            return redirect(url_for('book_service_flow', service_id=service_id))
            
        user_id = session['user_id']
        try:
            execute_db('''
                UPDATE slots 
                SET is_booked = 1, booked_by = ?, payment_method = ?, payment_status = ?, status = 'Upcoming'
                WHERE id = ?
            ''', [user_id, payment_method, payment_status, slot_id])
            
            if payment_method == 'Online (Razorpay)':
                flash('Online payment successful! Appointment booked.', 'success')
            else:
                flash('Appointment booked successfully! Please pay cash at the salon.', 'success')
        except Exception as e:
            flash('Booking failed.', 'danger')
        return redirect(url_for('bookings'))
            
    # GET Request: Fetch available slots
    slots = query_db('''
        SELECT * FROM slots 
        WHERE service_id = ? AND is_booked = 0 AND status = 'Upcoming'
        ORDER BY date ASC, time ASC
    ''', [service_id])
    return render_template('select_payment.html', service=service, slots=slots)
        
    return redirect(url_for('bookings'))

# User Bookings Page
@app.route('/bookings')
def bookings():
    if 'user_id' not in session or session.get('is_admin'):
        flash('Please login to view your bookings.', 'warning')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    upcoming = query_db('''
        SELECT s.*, ser.name as service_name, ser.price as service_price
        FROM slots s
        JOIN services ser ON s.service_id = ser.id
        WHERE s.booked_by = ? AND s.status = 'Upcoming'
        ORDER BY s.date ASC, s.time ASC
    ''', [user_id])
    
    completed = query_db('''
        SELECT s.*, ser.name as service_name, ser.price as service_price
        FROM slots s
        JOIN services ser ON s.service_id = ser.id
        WHERE s.booked_by = ? AND s.status = 'Completed'
        ORDER BY s.date DESC, s.time DESC
    ''', [user_id])
    
    return render_template('bookings.html', upcoming=upcoming, completed=completed)

# Rate booking
@app.route('/rate_booking/<int:slot_id>', methods=['POST'])
def rate_booking(slot_id):
    if 'user_id' not in session or session.get('is_admin'):
        flash('Please login to rate bookings.', 'warning')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    rating = request.form.get('rating')
    review = request.form.get('review')
    
    # Check if this completed booking belongs to the logged-in user
    booking = query_db('SELECT * FROM slots WHERE id = ? AND booked_by = ? AND status = "Completed"', [slot_id, user_id], one=True)
    if not booking:
        flash('Booking not found or not eligible for rating.', 'danger')
        return redirect(url_for('bookings'))
        
    try:
        execute_db('UPDATE slots SET rating = ?, review = ? WHERE id = ?', [rating, review, slot_id])
        flash('Thank you for your rating and review!', 'success')
    except Exception as e:
        flash('Failed to submit rating.', 'danger')
        
    return redirect(url_for('bookings'))

# User Profile View & Edit
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session or session.get('is_admin'):
        flash('Please login as a user to view your profile.', 'warning')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        location = request.form.get('location')
        
        if not name or not phone or not location:
            flash('All fields are required.', 'danger')
            return redirect(url_for('profile'))
            
        # Get current user details
        user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
        filename = user['image_path']
        
        # Handle profile image update
        file = request.files.get('image')
        if file and file.filename != '':
            if allowed_file(file.filename):
                new_filename = secure_filename(file.filename)
                # Ensure unique filename
                base, ext = os.path.splitext(new_filename)
                count = 1
                while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], new_filename)):
                    new_filename = f"{base}_{count}{ext}"
                    count += 1
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                filename = new_filename
            else:
                flash('Invalid file extension. Allowed images: png, jpg, jpeg, gif', 'danger')
                return redirect(url_for('profile'))
                
        try:
            execute_db('''
                UPDATE users 
                SET name = ?, phone = ?, location = ?, image_path = ?
                WHERE id = ?
            ''', [name, phone, location, filename, user_id])
            
            # Update session variables
            session['user_name'] = name
            session['user_image'] = filename
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            flash('Failed to update profile.', 'danger')
            
        return redirect(url_for('profile'))
        
    # GET: fetch user details
    user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
    return render_template('profile.html', user=user)

# --- Admin Modules ---

# Admin Customer Bookings Page
@app.route('/admin/bookings')
def admin_bookings():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    bookings = query_db('''
        SELECT s.*, ser.name as service_name, ser.price as service_price, 
               u.name as user_name, u.phone as user_phone, u.email as user_email, 
               u.location as user_location, u.image_path as user_image
        FROM slots s
        JOIN services ser ON s.service_id = ser.id
        JOIN users u ON s.booked_by = u.id
        ORDER BY s.date DESC, s.time DESC
    ''')
    return render_template('admin_bookings.html', bookings=bookings)

# Admin Dashboard (Manages Services)
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        image_path = request.form.get('image_path', 'service-1.jpg') # Default fallback
        
        if not name or not price or not description:
            flash('All fields are required.', 'danger')
        else:
            try:
                execute_db('INSERT INTO services (name, price, description, image_path) VALUES (?, ?, ?, ?)', [name, float(price), description, image_path])
                flash('Service added successfully!', 'success')
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                flash('Failed to add service.', 'danger')
                
    services_list = query_db('SELECT * FROM services')
    return render_template('admin_dashboard.html', services=services_list)

# Admin complete booking
@app.route('/admin/complete_slot/<int:slot_id>', methods=['POST'])
def complete_slot(slot_id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    try:
        execute_db('UPDATE slots SET status = "Completed" WHERE id = ?', [slot_id])
        flash('Booking marked as completed!', 'success')
    except Exception as e:
        flash('Failed to update booking status.', 'danger')
        
    referrer = request.referrer
    if referrer and 'admin/bookings' in referrer:
        return redirect(url_for('admin_bookings'))
    return redirect(url_for('admin_dashboard'))

# Admin services list redirect
@app.route('/admin/services')
def admin_services():
    return redirect(url_for('admin_dashboard'))

# Admin delete service
@app.route('/admin/delete_service/<int:service_id>', methods=['POST'])
def delete_service(service_id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    try:
        # Check if service is associated with slots
        slots_linked = query_db('SELECT COUNT(*) FROM slots WHERE service_id = ?', [service_id], one=True)[0]
        if slots_linked > 0:
            flash('Cannot delete service because it has slots assigned to it. Remove slots first.', 'danger')
        else:
            execute_db('DELETE FROM services WHERE id = ?', [service_id])
            flash('Service deleted successfully.', 'success')
    except Exception as e:
        flash('Failed to delete service.', 'danger')
        
    return redirect(url_for('admin_dashboard'))

# Admin slots list & add slots
@app.route('/admin/slots', methods=['GET', 'POST'])
def admin_slots():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        date = request.form.get('date')
        time = request.form.get('time')
        service_id = request.form.get('service_id')
        
        if not date or not time or not service_id:
            flash('All fields are required.', 'danger')
        else:
            try:
                # Add slot
                execute_db('INSERT INTO slots (date, time, service_id, is_booked) VALUES (?, ?, ?, 0)', [date, time, int(service_id)])
                flash('Booking slot created successfully!', 'success')
                return redirect(url_for('admin_slots'))
            except Exception as e:
                flash('Failed to create slot.', 'danger')
                
    services_list = query_db('SELECT * FROM services')
    
    # Get all slots (both booked and unbooked)
    all_slots = query_db('''
        SELECT s.*, ser.name as service_name, u.name as user_name
        FROM slots s
        JOIN services ser ON s.service_id = ser.id
        LEFT JOIN users u ON s.booked_by = u.id
        ORDER BY s.date DESC, s.time DESC
    ''')
    
    return render_template('admin_slots.html', services=services_list, slots=all_slots)

# Admin delete slot
@app.route('/admin/delete_slot/<int:slot_id>', methods=['POST'])
def delete_slot(slot_id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('login'))
        
    try:
        execute_db('DELETE FROM slots WHERE id = ?', [slot_id])
        flash('Slot deleted successfully.', 'success')
    except Exception as e:
        flash('Failed to delete slot.', 'danger')
        
    return redirect(url_for('admin_slots'))

if __name__ == '__main__':
    app.run(debug=True)
