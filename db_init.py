import sqlite3
import os
from datetime import datetime, timedelta

def init_db():
    persistent_dir = '/data'
    if os.path.exists(persistent_dir):
        db_path = os.path.join(persistent_dir, 'database.db')
        # Ensure uploads directory exists on persistent volume
        uploads_dir = os.path.join(persistent_dir, 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        # Copy default assets if they are present locally but missing in persistent volume
        import shutil
        for default_img in ['default-user.jpg', 'admin.png']:
            src = os.path.join('static', 'uploads', default_img)
            dst = os.path.join(uploads_dir, default_img)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    shutil.copy(src, dst)
                    print(f"Copied {default_img} to persistent disk uploads directory.")
                except Exception as e:
                    print(f"Error copying default asset: {e}")
    else:
        db_path = 'database.db'
    
    # Connect and create tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            location TEXT NOT NULL,
            image_path TEXT,
            password TEXT NOT NULL
        )
    ''')
    
    # 2. Services table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT NOT NULL
        )
    ''')
    
    # 3. Slots table (includes booking status, client details, ratings, payment)
    cursor.execute('DROP TABLE IF EXISTS slots')
    cursor.execute('''
        CREATE TABLE slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            service_id INTEGER NOT NULL,
            is_booked INTEGER DEFAULT 0,
            booked_by INTEGER,
            rating INTEGER,
            review TEXT,
            status TEXT DEFAULT 'Upcoming',
            payment_method TEXT,
            payment_status TEXT,
            FOREIGN KEY(service_id) REFERENCES services(id),
            FOREIGN KEY(booked_by) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    
    # Seed default services if they don't exist
    cursor.execute('SELECT COUNT(*) FROM services')
    if cursor.fetchone()[0] == 0:
        default_services = [
            ("Hair Styling & Spa", 1500.0, "Professional haircuts, styling, blow dry, coloring, and complete hair spa treatments.", "service-1.jpg"),
            ("Skincare & Facials", 2500.0, "Advanced facial treatments, skin tightening, masks, and revitalizing skin massage.", "service-2.jpg"),
            ("Makeup & Makeovers", 4000.0, "Bridal makeovers, event cosmetics styling, party makeups, and professional face prep.", "service-3.jpg"),
            ("Manicure & Pedicure", 1200.0, "Nail extensions, custom nail art, deep cleaning manicure, and pedicure spa massage.", "service-4.jpg")
        ]
        cursor.executemany('INSERT INTO services (name, price, description, image_path) VALUES (?, ?, ?, ?)', default_services)
        conn.commit()
        print("Default services seeded successfully.")

    # Seed default slots for the next 7 days if they don't exist
    cursor.execute('SELECT COUNT(*) FROM slots')
    if cursor.fetchone()[0] == 0:
        cursor.execute('SELECT id FROM services')
        service_ids = [row[0] for row in cursor.fetchall()]
        
        today = datetime.now()
        times = ["09:00 AM", "11:00 AM", "02:00 PM", "04:00 PM", "06:00 PM"]
        
        slots_to_seed = []
        for i in range(1, 6):  # Next 5 days
            date_str = (today + timedelta(days=i)).strftime("%Y-%m-%d")
            for idx, s_id in enumerate(service_ids):
                # Distribute times among services to avoid overlap at seed
                t = times[(idx + i) % len(times)]
                slots_to_seed.append((date_str, t, s_id, 0, None, None, None, 'Upcoming', None, None))
        
        cursor.executemany('''
            INSERT INTO slots (date, time, service_id, is_booked, booked_by, rating, review, status, payment_method, payment_status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', slots_to_seed)
        conn.commit()
        print("Default slots seeded successfully.")
        
    conn.close()

if __name__ == '__main__':
    init_db()
