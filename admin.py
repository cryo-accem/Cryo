import MySQLdb
from werkzeug.security import generate_password_hash

# --- Database Config ---
MYSQL_HOST = "localhost"
MYSQL_USER = "root"          # ⚠️ change if needed
MYSQL_PASSWORD = ""          # ⚠️ add your MySQL password
MYSQL_DBNAME = "cryo_em_db"

def set_admin(username, password, email="admin@cryoem.com"):
    try:
        # connect to DB
        conn = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DBNAME
        )
        cur = conn.cursor()

        # hash the password
        hashed_pw = generate_password_hash(password)

        # ensure table exists
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE,
            email VARCHAR(150) UNIQUE,
            password_hash VARCHAR(255),
            role ENUM('user','admin') DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # check if admin already exists
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing = cur.fetchone()

        if existing:
            # update password if exists
            cur.execute("UPDATE users SET password_hash=%s, role='admin' WHERE username=%s", (hashed_pw, username))
            print(f"✅ Admin user '{username}' updated successfully")
        else:
            # insert new admin
            cur.execute("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'admin')",
                        (username, email, hashed_pw))
            print(f"✅ Admin user '{username}' created successfully")

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ Error:", e)


if __name__ == "__main__":
    # --- Change these values as needed ---
    admin_username = "admin"
    admin_password = "admin@123"   # ⚠️ Choose a strong password!
    admin_email = "admin@cryoem.com"


    set_admin(admin_username, admin_password, admin_email)
